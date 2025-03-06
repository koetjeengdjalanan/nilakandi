
import sys
from datetime import datetime as dt
from time import sleep
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management.base import BaseCommand

from nilakandi.helper import azure_api
from nilakandi.models import Subscription
from nilakandi.tasks import grab_services



class Command(BaseCommand):
    help = "Populate the database with data from Azure API"


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
            default=(dt.now() - relativedelta(days=364)).date().isoformat(),
            help="[string: yyyy-mm-dd] Start date for data gathering",
        )
        parser.add_argument(
            "--delay",
            "-d",
            type=float,
            default=0.5,
            help="Delay between processing each subscription (in seconds)",
        )
        parser.add_argument(
            "--end-date",
            "-e",
            type=str,
            default=dt.now().date().isoformat(),
            help="[string: yyyy-mm-dd] End date for data gathering",
        )

    def handle(self, *args, **options):
        start_date = dt.fromisoformat(options["start_date"]).replace(
            tzinfo=ZoneInfo(settings.TIME_ZONE)
        )
        end_date = dt.fromisoformat(options["end_date"]).replace(
            tzinfo=ZoneInfo(settings.TIME_ZONE)
        )
        # logger = logging.getLogger(__name__)
        # logger.info(f"{start_date=}, {end_date=}, Deltas = {end_date - start_date}")

        auth = azure_api.Auth(
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
            tenant_id=settings.AZURE_TENANT_ID,
        )
        azure_api.Subscriptions(auth=auth).get().db_save()

        sys.stdout.write(
            f"{Subscription.objects.count()=} {", ".join(list(Subscription.objects.values_list('display_name', flat=True)))}\n"
        )
        for sub in Subscription.objects.all():
            grab_services.delay(
                bearer=auth.token.token,
                subscription_id=sub.subscription_id,
                start_date=start_date,
                end_date=end_date,
            )
            sleep(options["delay"])

