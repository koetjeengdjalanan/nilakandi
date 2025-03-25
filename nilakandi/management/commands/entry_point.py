import logging

from django.db.models import Model
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.models import User

from config.env import env

from nilakandi.models import (
    Subscription,
    Services,
    Operation,
    Marketplace,
    VirtualMachine,
    VirtualMachineCost,
    ExportHistory,
)


class Command(BaseCommand):
    help = "Initialize the application | Migrate Database and populate with data"

    def handle(self, *args, **options):
        logging.getLogger("django").info("Initializing application...")
        call_command("makemigrations", "nilakandi", interactive=False)
        logging.getLogger("django.db").info("Migrating database...")
        call_command("migrate", interactive=False)
        logging.getLogger("django.db").info("Populating database...")
        call_command("populate_db", "--start-date=20210101", interactive=False)
        models: tuple[str, Model] = (
            ("Subscription", Subscription),
            ("Services", Services),
            ("Operation", Operation),
            ("Marketplace", Marketplace),
            ("VirtualMachine", VirtualMachine),
            ("VirtualMachineCost", VirtualMachineCost),
            ("ExportHistory", ExportHistory),
        )
        for model in models:
            if model[1].objects.exist():
                logging.getLogger("django.db").info(msg=f"{model[0]} Creation Success!")
                logging.getLogger("django.db").info(
                    msg=f"{model[0]} Data Count: {model[1].objects.count()}"
                )
            else:
                logging.getLogger("django.db").error(msg=f"{model[0]} Creation Failed!")
        logging.getLogger("django").info("Creating superuser...")
        super_user = User.objects.create_superuser(
            username=env(var="NILAKANDI_SUPER_USER_USERNAME", default="arjuna"),
            password=env(
                var="NILAKANDI_SUPER_USER_PASSWORD", default="arjunamencaricinta"
            ),
            email=env(
                var="NILAKANDI_SUPER_USER_EMAIL", default="arjuna@nilakandi.local"
            ),
        )
        self.stdout.writelines(
            (
                self.style.NOTICE(
                    text="Please take note of this superuser credentials:\n"
                ),
                f"UserName: {super_user.username}\n",
                f"Password: {super_user.password}\n",
                f"Email   : {super_user.email}\n",
            )
        )
        logging.getLogger("django").info("Application initialized.")
        self.stdout.write("Done.")
