import logging
import sys
from datetime import datetime as dt
from time import sleep
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management.base import BaseCommand

from nilakandi.helper import azure_api
from nilakandi.models import Subscription
from nilakandi.tasks import (
    grab_blobs,
    grab_cost_export_history,
    grab_marketplaces,
    grab_services,
)


class Command(BaseCommand):
    help = "Populate the database with data from Azure API"

    def add_arguments(self, parser):
        parser.add_argument(
            "--subscription",
            type=str,
            nargs="*",
            default=None,
            help="Gather data from a specific list of subscription",
        )
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
        logging.getLogger("django").warning(f"Populating database, {options=}")
        start_date = dt.fromisoformat(options["start_date"]).replace(
            tzinfo=ZoneInfo(settings.TIME_ZONE)
        )
        end_date = dt.fromisoformat(options["end_date"]).replace(
            tzinfo=ZoneInfo(settings.TIME_ZONE)
        )

        auth = azure_api.Auth(
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
            tenant_id=settings.AZURE_TENANT_ID,
        )
        azure_api.Subscriptions(auth=auth).get().db_save()
        subs_id_list: list[str] = [
            str(id)
            for id in Subscription.objects.values_list("subscription_id", flat=True)
        ]
        if options["subscription"] in subs_id_list:
            subs_id_list = options["subscription"]
            sys.stdout.write(f"Processing for: {', '.join(subs_id_list)}\n")
        elif options["subscription"] is not None:
            sys.stderr.write(
                f"Subscription ID not found in database. Please use one of the following: {', '.join(subs_id_list)}\n"
            )
            sys.exit(2)

        sys.stdout.write(
            f"{Subscription.objects.count()=} {", ".join(list(Subscription.objects.values_list('display_name', flat=True)))}\n"
        )
        for id in subs_id_list:
            sub: str = Subscription.objects.get(subscription_id=id).display_name
            logging.getLogger("django").info(f"Processing for: {sub}")
            grab_services.delay(
                bearer=auth.token.token,
                subscription_id=id,
                start_date=start_date,
                end_date=end_date,
            )
            grab_marketplaces.delay(
                creds={
                    "client_id": settings.AZURE_CLIENT_ID,
                    "client_secret": settings.AZURE_CLIENT_SECRET,
                    "tenant_id": settings.AZURE_TENANT_ID,
                },
                subscription_id=id,
                start_date=start_date,
                end_date=end_date,
            )
            grab_cost_export_history.delay(bearer=auth.token.token, subscription_id=id)
            grab_blobs.delay(
                creds={
                    "client_id": settings.AZURE_CLIENT_ID,
                    "client_secret": settings.AZURE_CLIENT_SECRET,
                    "tenant_id": settings.AZURE_TENANT_ID,
                },
                subscription_id=id,
                start_date=start_date,
                end_date=end_date,
            )
            sleep(options["delay"])
        logging.getLogger("django").info("Task has been queued")
