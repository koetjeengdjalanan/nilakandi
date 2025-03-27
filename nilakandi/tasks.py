from datetime import datetime
from uuid import UUID

from celery import shared_task
from dateutil.relativedelta import relativedelta

from nilakandi.azure.api.costexport import ExportHistory, ExportOrCreate
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
    month_list = [
        (start_date + relativedelta(months=i)).strftime("%Y%m")
        for i in range(
            (end_date.year - start_date.year) * 12
            + end_date.month
            - start_date.month
            + 1
        )
    ]
    for month in month_list:
        azi.Marketplaces(
            auth=auth,
            subscription=sub,
            date=month,
        ).get().db_save()


@shared_task(name="nilakandi.tasks.cost_export")
def export_costs_to_blob(
    bearer: str,
    subscription_id: UUID,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, any]]:
    """
    Export costs to a blob storage for a given subscription within a date range.

    Args:
        bearer (str): The bearer token for authentication.
        subscription_id (UUID): The subscription ID for which costs are to be exported.
        start_date (datetime): The start date of the export period.
        end_date (datetime): The end date of the export period.

    Returns:
        list[dict[str, any]]: A list of dictionaries containing the exported cost data.
    """
    exports = []
    current = start_date
    while current < end_date:
        end_of_month = datetime.combine(
            current + relativedelta(month=0, day=31), datetime.min.time()
        )
        if end_of_month > end_date:
            end_of_month = end_date
        eoc = (
            ExportOrCreate(
                bearer_token=bearer,
                subscription=subscription_id,
                start_date=current,
                end_date=end_of_month,
            )
            .exec()
            .run()
        )
        exports.append(eoc.res)
        current = datetime.combine(
            end_of_month + relativedelta(days=1), datetime.min.time()
        )
    return exports


@shared_task(name="nilakandi.tasks.grab_cost_export_history")
def grab_cost_export_history(
    bearer: str,
    subscription_id: UUID,
) -> dict[str, any]:
    """
    Retrieves and saves the cost export history for a given subscription.

    Args:
        bearer (str): The bearer token for authentication.
        subscription_id (UUID): The unique identifier for the subscription.

    Returns:
        dict[str, any]: A dictionary containing the result of the export history retrieval and save operation.
    """
    res = (
        ExportHistory(
            bearer_token=bearer,
            subscription=subscription_id,
        )
        .pull()
        .db_save()
    )
    return res.res
