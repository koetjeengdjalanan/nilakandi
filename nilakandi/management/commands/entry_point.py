import logging

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.models import User

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
        logging.getLogger("django").info("Initializing application...")
        call_command("makemigrations", "nilakandi", interactive=False)
        logging.getLogger("django.db").info("Migrating database...")
        call_command("migrate", interactive=False)
        logging.getLogger("django.db").info("Populating database...")
        call_command("populate_db", start_date="20250201")
        logging.getLogger("django").info("Creating superuser...")
        su_creds: dict[str, str] = {
            "user_name": env(var="NILAKANDI_SUPER_USER_USERNAME", default="arjuna"),
            "password": env(
                var="NILAKANDI_SUPER_USER_PASSWORD", default="arjunamencaricinta"
            ),
            "email": env(
                var="NILAKANDI_SUPER_USER_EMAIL", default="arjuna@nilakandi.local"
            ),
        }
        if User.objects.get(username=su_creds["user_name"]):
            logging.getLogger("django").info(
                "Superuser already exists. Skipping superuser creation."
            )
        else:
            User.objects.create_superuser(
                username=su_creds["user_name"],
                password=su_creds["password"],
                email=su_creds["email"],
            )
            self.stdout.writelines(
                (
                    self.style.NOTICE(
                        text="Please take note of this superuser credentials:\n"
                    ),
                    f"UserName: {su_creds['user_name']}\n",
                    f"Password: {su_creds['password']}\n",
                    f"Email   : {su_creds['email']}\n",
                )
            )
        logging.getLogger("django").info("Application initialized.")
        try:
            call_command("runserver", "0.0.0.0:21180")
        except KeyboardInterrupt:
            logging.getLogger("django").critical("Application terminated.")
            exit(1)
