from time import sleep
from celery import shared_task
from datetime import datetime as dt, timezone, timedelta
from uuid import UUID

from nilakandi.azure.api.services import Services
from nilakandi.helper import azure_api as azi
from nilakandi.helper.miscellaneous import yearly_list
from nilakandi.models import Subscription as SubscriptionsModel
from nilakandi.helper import azure_api as azi


@shared_task
def grab_services(creds: dict[str, str], subscription_id: UUID, start_date: dt.date, end_date: dt.date, skip_existing: bool = False) -> None:
    """Grab Services data from Azure API with the given parameters.

    Args:
        creds (dict[str, str]): Azure API credentials dictionary.
        subscription_id (UUID): Subscription ID.
        start_date (dt.date): Start Date for the data gathering.
        end_date (dt.date): End date for the data gathering.
        skip_existing (bool, optional): Skip if data is existed in the databases. Defaults to False.

    Raises:
        NotImplementedError: skip_existing=True is not implemented yet.
    """
    if skip_existing:
        raise NotImplementedError("skip_existing=True is not implemented yet.")
    auth = azi.Auth(
        client_id=creds['client_id'],
        tenant_id=creds['tenant_id'],
        client_secret=creds['client_secret']
    )
    sub = SubscriptionsModel.objects.get(subscription_id=subscription_id)
    # earliest: dt.date = sub.services_set.earliest('usage_date').usage_date
    # latest: dt.date = sub.services_set.latest('usage_date').usage_date
    loopedDate = start_date
    while loopedDate <= end_date:
        deltaDays: int = (
            3 if (end_date - start_date).days >= 3 else (end_date - start_date).days
        )
        tempDate = loopedDate + timedelta(days=deltaDays)
        # TODO: Implement skip_existing
        # if skip_existing and (loopedDate >= earliest) and (tempDate <= latest):
        #     continue
        services = azi.Services(
            auth=auth,
            subscription=sub,
            start_date=loopedDate,
            end_date=tempDate,
        )
        services.get().db_save()
        sleep(.75)
        loopedDate += timedelta(days=deltaDays+1)


@shared_task
def grab_marketplaces(creds: dict[str, str], subscription_id: UUID, start_date: dt.date, end_date: dt.date, skip_existing: bool = False) -> None:
    """Grab Marketplaces data from Azure API with the given parameters.

    Args:
        creds (dict[str, str]): Azure API credentials dictionary.
        subscription_id (UUID): Subscription ID.
        start_date (dt.date): Start Date for the data gathering.
        end_date (dt.date): End date for the data gathering.
        skip_existing (bool, optional): Skip if data is existed in the databases. Defaults to False.

    Raises:
        NotImplementedError: skip_existing=True is not implemented yet.
    """
    if skip_existing:
        raise NotImplementedError("skip_existing=True is not implemented yet.")
    auth = azi.Auth(
        client_id=creds['client_id'],
        tenant_id=creds['tenant_id'],
        client_secret=creds['client_secret']
    )
    sub = SubscriptionsModel.objects.get(subscription_id=subscription_id)
    # earliest: dt.date = sub.marketplace_set.earliest('usage_start').usage_start
    # latest: dt.date = sub.marketplace_set.latest('usage_end').usage_end
    loopedDate = start_date
    while loopedDate <= end_date:
        deltaDays: int = 3 if (
            end_date - start_date).days >= 3 else (end_date - start_date).days
        tempDate = loopedDate + timedelta(days=deltaDays)
        marketplace = azi.Marketplace(
            auth=auth,
            subscription=sub,
            start_date=loopedDate,
            end_date=tempDate,
        )
        marketplace.get().db_save()
        sleep(.75)
        loopedDate += timedelta(days=deltaDays+1)
