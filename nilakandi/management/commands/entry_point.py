"""Nilakandi App Initializer Command!"""

import logging
import os
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.migrations.recorder import MigrationRecorder
from django.db.utils import ProgrammingError as DjangoProgrammingError
from psycopg2.errors import UndefinedTable

from config.env import env


class Command(BaseCommand):
    """The entry point for running the app.

    Command to initialize the application by performing the following steps:
    1. Log the initialization process.
    2. Make migrations for the 'nilakandi' app.
    3. Migrate the database.
    4. Populate the database with initial data.
    5. Verify the creation and data count of specific models.
    6. Create a superuser with credentials from environment variables.
    7. Log the superuser credentials.
    8. Start the Django development server.

    Attributes:
        help (str): Description of the command.

    Methods:
        handle(self, *args, **options): Executes the command steps.
    """

    help = (
        "Initializes the application by making migrations, migrating the database,"
        "populating initial data, creating a superuser, and starting the server."
    )

    def add_arguments(self, parser):
        """Add command-line options for the management command.

        This method registers the "--nopopulate" flag, which when present
        will skip the database population step (useful if you don't want
        to pull data from Azure).

        Args:
            parser (argparse.ArgumentParser): The argument parser instance
                to which this command's options will be added.
        """
        parser.add_argument(
            "--nopopulate",
            action="store_true",
            default=False,
            help="Skip database population. Only do this if you don't want to pull from Azure!",
        )

    def handle(self, *args, **options):
        """Entry point for the custom Django management command that initializes (if necessary).

        Then starts the application using Gunicorn.

        Behavior overview:
        1. Determines whether the application has already been initialized by querying the
            migration history (MigrationRecorder). If there are no recorded migrations (or the
            migration table does not yet exist), it assumes a fresh database and performs full
            initialization; otherwise it skips directly to server startup.
        2. Fresh initialization sequence (init_app):
            - Ensures the migrations package (migrations/__init__.py) exists for the 'nilakandi' app
              to avoid makemigrations failing on a missing directory/package.
            - Runs makemigrations for the 'nilakandi' app explicitly, then applies migrations for
              that app, followed by all remaining project apps.
            - Verifies basic migration success by querying MigrationRecorder and importing and
              touching a model (Subscription) to surface potential table/ORM mismatches early.
            - Invokes a custom "populate_db" management command using settings.EARLIEST_DATA as
              a starting point to seed initial domain data.
            - Creates a Django superuser if one does not already exist. The credentials are sourced
              from environment variables (NILAKANDI_SUPER_USER_USERNAME, NILAKANDI_SUPER_USER_PASSWORD,
              NILAKANDI_SUPER_USER_EMAIL) with documented defaults and are echoed (username/email/password)
              to stdout with a NOTICE style the first time they are created.
        3. Common finalization sequence (finishing):
            - Runs "collectstatic" non-interactively (verbosity suppressed) to prepare static assets.
            - Replaces the current process with Gunicorn via os.execvp, using the configuration at
              /app/gunicorn.conf.py and the WSGI target "config.wsgi:application". After execvp
              the Python interpreter for this management command does not return.
        4. Robust logging is performed throughout using the "django" and "django.db" loggers with
            emoji markers for operational clarity.

        Control flow & error handling:
        - If migration metadata lookup raises UndefinedTable or DjangoProgrammingError, the command
          treats the situation as an uninitialized database and proceeds with initialization.
        - Any unexpected exception during initialization is logged at critical level and the process
          exits with a non-zero status.
        - KeyboardInterrupt during server start triggers a critical log and exits with status 1.

        Environment / side effects:
        - Modifies the database schema and data (migrations, seeding, superuser creation).
        - Writes static files to STATIC_ROOT via collectstatic.
        - Replaces the current process with a Gunicorn master process (no return path).
        - Emits superuser credentials to stdout only on first creation (consider rotating them
          after deployment in production environments).

        Parameters:
        *args: Positional arguments passed by Django's management command interface (unused here).
        **options: Keyword arguments supplied by Django's management command interface (unused here).

        Returns:
             None. This method either:
                - Terminates the process via os.execvp (on successful run), or
                - Exits with a non-zero status code on unrecoverable error.

        Raises:
             Propagates unexpected exceptions during migration verification or initialization
             after logging; normal operation path does not return.
        """

        def finishing():
            logging.getLogger("django").info("📡 Starting the server...")
            try:
                call_command("collectstatic", interactive=False, verbosity=0)
                gunicorn_args = [
                    "gunicorn",
                    "--config",
                    f"{settings.BASE_DIR}/gunicorn.conf.py",  # Assumes gunicorn.conf.py is in the project root
                    "config.asgi:application",  # ASGI target (was config.wsgi:application)
                ]
                os.execvp("gunicorn", gunicorn_args)
            except KeyboardInterrupt:
                logging.getLogger("django").critical("☠️ Application terminated.")
                exit(1)

        def init_app():
            logging.getLogger("django").info("👣 Initializing application...")
            # call_command("makemigrations", interactive=False) # Removed this line

            # Ensure migrations directory and __init__.py exist for 'nilakandi' app
            try:
                app_config = django_apps.get_app_config("nilakandi")
                migrations_dir = Path(app_config.path) / "migrations"
                migrations_dir.mkdir(parents=True, exist_ok=True)
                init_file = migrations_dir / "__init__.py"
                if not init_file.exists():
                    init_file.touch()
                logging.getLogger("django").info(
                    f"Ensured migrations directory and __init__.py for 'nilakandi' app at {migrations_dir}"
                )
            except Exception as e:
                logging.getLogger("django").error(f"Error ensuring migrations directory for 'nilakandi': {e}")
                # Allow makemigrations to proceed and potentially fail with its own error if this step fails.

            call_command("makemigrations", "nilakandi", interactive=False)
            logging.getLogger("django.db").info("💽 Migrating database (nilakandi app)...")
            call_command("migrate", "nilakandi", interactive=False)  # Migrate nilakandi specifically
            logging.getLogger("django.db").info("💽 Migrating database (remaining apps)...")
            call_command("migrate", interactive=False)  # Migrate other apps (auth, admin, etc.)

            try:
                logging.getLogger("django.db").info("🔎 Verifying table creation after migration...")

                if not MigrationRecorder.Migration.objects.exists():
                    pass

                from nilakandi.models import Subscription

                if not Subscription.objects.exists():
                    pass

                logging.getLogger("django.db").info("✅ Tables appear to be created/verified after migration.")

            except DjangoProgrammingError as e:
                logging.getLogger("django.db").error(f"❌ Database tables not created or verified after migrate: {e}")
                raise
            except Exception as e:
                logging.getLogger("django.db").error(
                    f"❌ Unexpected error during table verification after migrate: {e}"
                )
                raise

            if options["nopopulate"]:
                logging.getLogger("django").info("👌 Skipping database population as per --nopopulate flag.")
            else:
                logging.getLogger("django.db").info("💽 Populating database...")
                call_command("populate_db", start_date=settings.EARLIEST_DATA)
            logging.getLogger("django").info("🦸 Creating superuser...")
            su_creds: dict[str, str] = {
                "user_name": env(var="NILAKANDI_SUPER_USER_USERNAME", default="arjuna"),  # type: ignore
                "password": env(var="NILAKANDI_SUPER_USER_PASSWORD", default="arjunamencaricinta"),  # type: ignore
                "email": env(var="NILAKANDI_SUPER_USER_EMAIL", default="arjuna@nilakandi.local"),  # type: ignore
            }  # type: ignore
            try:
                User.objects.get(username=su_creds["user_name"])
                logging.getLogger("django").info("🦸 Superuser already exists. Skipping superuser creation.")
            except User.DoesNotExist:
                User.objects.create_superuser(
                    username=su_creds["user_name"],
                    password=su_creds["password"],
                    email=su_creds["email"],
                )
                self.stdout.writelines(
                    (
                        self.style.NOTICE(text="✒️ Please take note of this superuser credentials:\n"),
                        f"UserName: {su_creds['user_name']}\n",
                        f"Password: {su_creds['password']}\n",
                        f"Email   : {su_creds['email']}\n",
                    )
                )
            logging.getLogger("django").info("Application initialized.")

        try:
            logging.getLogger("django").info("📋 Checking if the application is already initialized...")
            check = [(m.app, m.name) for m in MigrationRecorder.Migration.objects.all()]
            if not check:
                raise UndefinedTable("No migrations recorded, assuming fresh database.")
            logging.getLogger("django").info("🥳 Application is already initialized.")
            finishing()
        except (
            UndefinedTable,
            DjangoProgrammingError,
        ):
            logging.getLogger("django").info("✒️ Application is to be initialized")
            init_app()
            finishing()
        except Exception as e:
            logging.getLogger("django").critical("❌ An error occurred during initialization: %s", e)
            exit(1)
