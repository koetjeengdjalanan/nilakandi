from datetime import datetime as dt
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management.base import BaseCommand

from nilakandi.azure.api.services import Services
from nilakandi.helper import azure_api
from nilakandi.models import Subscription as subs


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
            "--end-date",
            "-e",
            type=str,
            default=dt.now().date().isoformat(),
            help="[string: yyyy-mm-dd] End date for data gathering",
        )

    def handle(self, *args, **options):
        startDate = dt.fromisoformat(options["start_date"]).replace(
            tzinfo=ZoneInfo(settings.TIME_ZONE)
        )
        endDate = dt.fromisoformat(options["end_date"]).replace(
            tzinfo=ZoneInfo(settings.TIME_ZONE)
        )
        print(f"{startDate=}, {endDate=}")
        auth = azure_api.Auth(
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
            tenant_id=settings.AZURE_TENANT_ID,
        )
        # azure_api.Subscriptions(auth=auth).get().db_save()
        for sub in subs.objects.all()[4:]:
            print(sub.display_name, sub.subscription_id, sep=": ")
            services = (
                Services(
                    bearer_token=auth.token.token,
                    subscription=sub,
                    start_date=startDate,
                    end_date=endDate,
                )
                .pull()
                .db_save()
            )
            print(services.res.data, sep="\n", end=f"\n{"="*100}>\n")
            while services.res.next_link:
                nextUrl = services.res.next_link
                services.pull(uri=nextUrl).db_save()
                print(services.res.data, sep="\n", end=f"\n{"="*100}>\n")
                # retries = 0
                # try:
                # except RequestException as e:
                #     if e.response.status_code != 429:
                #         raise e
                #     while services.res.status == 429 and retries < 5:
                #         if retries >= 6:
                #             raise e
                #         retries += 1
                #         print(
                #             f"Rate Limit Exceeded - Retry {retries}",
                #             services.res.headers,
                #             services.res.raw,
                #             f"sleeping for {services.res.headers['x-ms-ratelimit-microsoft.costmanagement-entity-retry-after']} seconds",
                #             sep="\n",
                #             end=f"\n{"="*100}>\n",
                #         )
                #         sleep(
                #             int(
                #                 services.res.headers[
                #                     "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after"
                #                 ]
                #             )
                #         )
                #         services.pull(uri=nextUrl).db_save()

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
