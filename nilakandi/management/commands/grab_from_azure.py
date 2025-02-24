from django.core.management.base import BaseCommand, no_translations
from django.conf import settings

from nilakandi.models import Subscription as SubscriptionsModel
from nilakandi.helper import azure_api

from datetime import datetime as dt, timezone, timedelta


class Command(BaseCommand):
    help = "Gather data from Azure API"

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
        def grab_services(sub: SubscriptionsModel) -> None:
            ...

        def grab_marketplaces(sub: SubscriptionsModel) -> None:
            ...

        startDate = dt.fromisoformat(options["start_date"]).date()
        endDate = dt.fromisoformat(options["end_date"]).date()
        if endDate < startDate:
            raise ValueError("End date must be later than start date.")
        if endDate > dt.now():
            raise ValueError("End date must be earlier than today.")

        auth = azure_api.Auth(
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
            tenant_id=settings.AZURE_TENANT_ID,
        )
        subs = SubscriptionsModel.objects.all()

        raise NotImplementedError("This command is not implemented yet.")
