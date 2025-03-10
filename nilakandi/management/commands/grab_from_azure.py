from django.core.management.base import BaseCommand, no_translations
from django.conf import settings

from nilakandi.models import Subscription as SubscriptionsModel
from nilakandi.helper import azure_api

from nilakandi.tasks import grab_services, grab_marketplaces


from datetime import datetime as dt, timezone, timedelta


class Command(BaseCommand):

    help = "Gather data from Azure API and save it to the database using celery as task queue."


    def add_arguments(self, parser):
        # parser.add_argument(
        #     "--all",
        #     action="store_true",
        #     help="Gather data from all subscriptions",
        # )
        # parser.add_argument(
        #     "--subscription",
        #     type=str,
        #     help="Gather data from a specific subscription",
        # )
        parser.add_argument(
            "--start-date",
            "-s",
            type=str,
            default=(dt.now()-timedelta(days=30)).date().isoformat(),
            help="[string: yyyy-mm-dd] Start date for data gathering",
        )
        parser.add_argument(
            "--end-date",
            "-e",
            type=str,
            default=dt.now().date().isoformat(),
            help="[string: yyyy-mm-dd] End date for data gathering",
        )

    @no_translations
    def handle(self, *args, **options):


        startDate = dt.fromisoformat(options["start_date"]).date()
        endDate = dt.fromisoformat(options["end_date"]).date()
        if endDate < startDate:
            raise ValueError("End date must be later than start date.")

        if endDate > dt.now().date():
            raise ValueError("End date must be earlier than today.")

        creds = {
            "client_id": str(settings.AZURE_CLIENT_ID),
            "tenant_id": str(settings.AZURE_TENANT_ID),
            "client_secret": str(settings.AZURE_CLIENT_SECRET),
        }
        subs = SubscriptionsModel.objects.all()
        for sub in subs:
            grab_services.delay(creds=creds, subscription_id=sub.subscription_id,
                                start_date=startDate, end_date=endDate)
            grab_marketplaces.delay(creds=creds, subscription_id=sub.subscription_id,
                                    start_date=startDate, end_date=endDate)
        self.stdout.write(self.style.SUCCESS(
            "Data gathering has been successfully queued."))

