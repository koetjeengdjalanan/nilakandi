from django.core.management.base import BaseCommand
from django.conf import settings

from nilakandi.models import Subscription as subs
from nilakandi.helper import azure_api

from datetime import datetime as dt, timezone, timedelta


class Command(BaseCommand):
    help = "Populate the database with data from Azure API"

    def handle(self, *args, **kwargs):
        auth = azure_api.Auth(
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
            tenant_id=settings.AZURE_TENANT_ID,
        )
        azure_api.Subscriptions(auth=auth).get().db_save()
        tzOffset = timedelta(hours=7)
        localTz = timezone(tzOffset)
        date = dt.now(localTz)
        for sub in subs.objects.all():
            print(sub.display_name, sub.subscription_id, sep=": ")
            services = azure_api.Services(
                auth=auth,
                subscription=sub,
                start_date=dt(year=date.year, month=date.month - 1, day=1),
                end_date=dt(
                    year=date.year, month=date.month - 1, day=1
                ),
            )
            services.get().db_save()
            serviceCount = sub.services_set.count()
            print("Service Count: ", serviceCount)
            marketplace = azure_api.Marketplaces(
                auth=auth,
                subscription=sub,
                date=dt(year=date.year, month=date.month - 1, day=1),
            )
            marketplace.get().db_save()
            marketplaceCount = sub.marketplace_set.count()
            print("Marketplace Count: ", marketplaceCount)
            print("=" * 25)
