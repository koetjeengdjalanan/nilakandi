
from datetime import datetime, timedelta
from time import sleep
from uuid import UUID

from celery import shared_task

from nilakandi.azure.api.services import Services
from nilakandi.helper import azure_api as azi
from nilakandi.helper.miscellaneous import yearly_list
from nilakandi.models import Subscription as SubscriptionsModel


@shared_task(name="nilakandi.tasks.grab_services")
def grab_services(
    bearer: str,
    subscription_id: UUID,
    start_date: datetime,
    end_date: datetime,
    skip_existing: bool = False,
) -> None:
    """Grab Services data from Azure API with the given parameters.

    Args:
        bearer (str): Bearer token for the Azure API.
        subscription_id (UUID): Subscription ID.
        start_date (datetime): date to start the data gathering.
        end_date (datetime): date to end the data gathering.
        skip_existing (bool, optional): Skip data if existed in DB. Defaults to False.

    Raises:
        NotImplementedError: skip_existing is not implemented yet.
    """
    if skip_existing:
        raise NotImplementedError("skip_existing=True is not implemented yet.")
    dates = yearly_list(start_date, end_date)
    for date in dates:
        start_date, end_date = date
        services = (
            Services(
                bearer_token=bearer,
                subscription=subscription_id,
                start_date=start_date,
                end_date=end_date,
            )
            .pull()
            .db_save()
        )
        # TODO: Implement Logging
        while services.res.next_link:
            nextUrl = services.res.next_link
            services.pull(uri=nextUrl).db_save()
            # TODO: Implement Logging


@shared_task(name="nilakandi.tasks.grab_marketplaces")
def grab_marketplaces(
    creds: dict[str, str],
    subscription_id: UUID,
    start_date: datetime.date,
    end_date: datetime.date,
    skip_existing: bool = False,
) -> None:
    """Grab Marketplaces data from Azure API with the given parameters.

    Args:
        creds (dict[str, str]): Azure API credentials dictionary.
        subscription_id (UUID): Subscription ID.
        start_date (datetime.date): Start Date for the data gathering.
        end_date (datetime.date): End date for the data gathering.
        skip_existing (bool, optional): Skip if data is existed in the databases. Defaults to False.

    Raises:
        NotImplementedError: skip_existing=True is not implemented yet.
    """
    if skip_existing:
        raise NotImplementedError("skip_existing=True is not implemented yet.")
    auth = azi.Auth(
        client_id=creds["client_id"],
        tenant_id=creds["tenant_id"],
        client_secret=creds["client_secret"],
    )
    sub = SubscriptionsModel.objects.get(subscription_id=subscription_id)
    # earliest: datetime.date = sub.marketplace_set.earliest('usage_start').usage_start
    # latest: datetime.date = sub.marketplace_set.latest('usage_end').usage_end
    loopedDate = start_date
    while loopedDate <= end_date:
        deltaDays: int = (
            3 if (end_date - start_date).days >= 3 else (end_date - start_date).days
        )
        tempDate = loopedDate + timedelta(days=deltaDays)
        marketplace = azi.Marketplaces(

            auth=auth,
            subscription=sub,
            start_date=loopedDate,
            end_date=tempDate,
        )

        marketplace.get().db_save()
        sleep(0.75)
        loopedDate += timedelta(days=deltaDays + 1)

