import logging
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
    """
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

    help = "Initializes the application by making migrations, migrating the database, populating initial data, creating a superuser, and starting the server."

    def handle(self, *args, **options):
        def finishing():
            logging.getLogger("django").info("📡 Starting the server...")
            try:
                call_command("runserver", "0.0.0.0:21180")
            except KeyboardInterrupt:
                logging.getLogger("django").critical("☠️ Application terminated.")
                exit(1)

        def init_app():
            logging.getLogger("django").info("👣 Initializing application...")

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
                logging.getLogger("django").error(
                    f"Error ensuring migrations directory for 'nilakandi': {e}"
                )
                # Allow makemigrations to proceed and potentially fail with its own error if this step fails.

            call_command("makemigrations", "nilakandi", interactive=False)
            logging.getLogger("django.db").info("💽 Migrating database...")
            call_command("migrate", interactive=False)

            try:
                logging.getLogger("django.db").info(
                    "🔎 Verifying table creation after migration..."
                )

                if not MigrationRecorder.Migration.objects.exists():
                    pass

                from nilakandi.models import Subscription

                if not Subscription.objects.exists():
                    pass

                logging.getLogger("django.db").info(
                    "✅ Tables appear to be created/verified after migration."
                )

            except DjangoProgrammingError as e:
                logging.getLogger("django.db").error(
                    f"❌ Database tables not created or verified after migrate: {e}"
                )
                raise
            except Exception as e:
                logging.getLogger("django.db").error(
                    f"❌ Unexpected error during table verification after migrate: {e}"
                )
                raise

            logging.getLogger("django.db").info("💽 Populating database...")
            call_command("populate_db", start_date=settings.EARLIEST_DATA)
            logging.getLogger("django").info("🦸 Creating superuser...")
            su_creds: dict[str, str] = {
                "user_name": env(var="NILAKANDI_SUPER_USER_USERNAME", default="arjuna"),  # type: ignore
                "password": env(
                    var="NILAKANDI_SUPER_USER_PASSWORD", default="arjunamencaricinta"  # type: ignore
                ),
                "email": env(
                    var="NILAKANDI_SUPER_USER_EMAIL", default="arjuna@nilakandi.local"  # type: ignore
                ),
            }  # type: ignore
            try:
                User.objects.get(username=su_creds["user_name"])
                logging.getLogger("django").info(
                    "🦸 Superuser already exists. Skipping superuser creation."
                )
            except User.DoesNotExist:
                User.objects.create_superuser(
                    username=su_creds["user_name"],
                    password=su_creds["password"],
                    email=su_creds["email"],
                )
                self.stdout.writelines(
                    (
                        self.style.NOTICE(
                            text="✒️ Please take note of this superuser credentials:\n"
                        ),
                        f"UserName: {su_creds['user_name']}\n",
                        f"Password: {su_creds['password']}\n",
                        f"Email   : {su_creds['email']}\n",
                    )
                )
            logging.getLogger("django").info("Application initialized.")

        try:
            logging.getLogger("django").info(
                "📋 Checking if the application is already initialized..."
            )
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
            logging.getLogger("django").critical(
                "❌ An error occurred during initialization: %s", e
            )
            exit(1)
