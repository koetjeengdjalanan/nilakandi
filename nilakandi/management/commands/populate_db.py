from time import sleep
from django.core.management.base import BaseCommand
from django.conf import settings
from requests import HTTPError

from nilakandi.models import Subscription as subs
from nilakandi.helper import azure_api

from datetime import datetime as dt
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo


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
            default=(dt.now()-relativedelta(months=1)).date().isoformat(),
            help="[string: yyyy-mm-dd] Start date for data gathering",
        )
        parser.add_argument(
            "--end-date",
            "-e",
            type=str,
            default=dt.now().date().isoformat(),
            help="[string: yyyy-mm-dd] End date for data gathering",
        )

    def handle(self, *args, **options):
        startDate = dt.fromisoformat(options["start_date"]).replace(
            tzinfo=ZoneInfo(settings.TIME_ZONE))
        endDate = dt.fromisoformat(options["end_date"]).replace(
            tzinfo=ZoneInfo(settings.TIME_ZONE))
        print(f"{startDate=}, {endDate=}")
        auth = azure_api.Auth(
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
            tenant_id=settings.AZURE_TENANT_ID,
        )
        azure_api.Subscriptions(auth=auth).get().db_save()
        for sub in subs.objects.all():
            print(sub.display_name, sub.subscription_id, sep=": ")
            services = azure_api.Services(
                auth=auth,
                subscription=sub,
                start_date=startDate,
                end_date=endDate,
            )
            services.get().db_save(check_conflic_on_create=False)
            while services.nextLink is not None:
                print(f"{services.nextLink=}")
                try:
                    services.next()
                except HTTPError as error:
                    sleep(60)
                services.db_save(check_conflic_on_create=False)
            serviceCount = sub.services_set.count()
            print("Service Count: ", serviceCount)
            # marketplace = azure_api.Marketplaces(
            #     auth=auth,
            #     subscription=sub,
            #     date=dt(year=date.year, month=date.month - 1, day=1),
            # )
            # marketplace.get().db_save()
            # marketplaceCount = sub.marketplace_set.count()
            # print("Marketplace Count: ", marketplaceCount)
            print("=" * 25)
