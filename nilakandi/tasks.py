import logging
from datetime import datetime
from functools import wraps
from uuid import UUID

from celery import current_task, shared_task
from dateutil.relativedelta import relativedelta

from nilakandi.azure.api.costexport import ExportHistory, ExportOrCreate
from nilakandi.azure.api.services import Services
from nilakandi.azure.models import BlobsInfo
from nilakandi.helper import azure_api as azi
from nilakandi.helper.azure_blob import Blobs
from nilakandi.helper.miscellaneous import yearly_list
from nilakandi.models import Subscription as SubscriptionsModel


def with_sub_name(task_func):
    """
    Decorator for task functions that adds subscription name to task headers.

    This decorator adds the subscription's display name to the task's headers
    when a subscription_id is provided in the function arguments.
    This information can be viewed in monitoring tools like Flower.

    Parameters:
        task_func (callable): The task function to be decorated.

    Returns:
        callable: The wrapped function that updates task headers before execution.
    """

    @wraps(task_func)
    def wrapper(*args, **kwargs):
        subscription_id = kwargs.get("subscription_id")
        if subscription_id:
            try:
                subscription = SubscriptionsModel.objects.get(
                    subscription_id=subscription_id
                ).display_name
                # Add subscription info to task headers
                if hasattr(current_task.request, "headers"):
                    if current_task.request.headers is None:
                        current_task.request.headers = {}
                    current_task.request.headers["subscription"] = subscription

                # Add subscription to task info for logging/tracking
                if not hasattr(current_task.request, "subscription"):
                    setattr(current_task.request, "subscription", subscription)

                # Log the subscription being processed
                logging.getLogger("nilakandi.tasks").info(
                    f"Processing {current_task.name} for subscription: {subscription}"
                )
            except Exception as e:
                logging.getLogger("nilakandi.tasks").error(
                    f"Error adding subscription info to task: {e}"
                )
        return task_func(*args, **kwargs)

    return wrapper


@shared_task(name="nilakandi.tasks.grab_services")
@with_sub_name
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
        try:
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
        except Exception as e:
            logging.getLogger("nilakandi.pull").error(
                f"Error in grabbing services for subscription {subscription_id}: {e}"
            )
        finally:
            continue
    return {
        "subscription_id": subscription_id,
        "subscription_name": SubscriptionsModel.objects.get(
            subscription_id=subscription_id
        ).display_name,
        "period": (start_date, end_date),
        "count": SubscriptionsModel.objects.get(
            subscription_id=subscription_id
        ).services_set.count(),
    }


@shared_task(name="nilakandi.tasks.grab_marketplaces")
@with_sub_name
def grab_marketplaces(
    creds: dict[str, str],
    subscription_id: UUID,
    start_date: datetime.date,
    end_date: datetime.date,
    skip_existing: bool = False,
) -> dict[str, any]:
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
        _ = azi.Marketplaces(
            auth=auth,
            subscription=sub,
            date=month,
        )
        try:
            _.get().db_save()
        except Exception as e:
            logging.getLogger("nilakandi.pull").error(
                f"Error in grabbing marketplaces for {sub.display_name} month {month}: {e}"
            )
        finally:
            continue
    return {
        "subscription_id": sub.subscription_id,
        "subscription_name": sub.display_name,
        "period": (start_date, end_date),
        "count": sub.marketplace_set.count(),
    }


@shared_task(name="nilakandi.tasks.cost_export")
@with_sub_name
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
@with_sub_name
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


@shared_task(name="nilakandi.tasks.grab_blobs")
@with_sub_name
def grab_blobs(
    creds: dict[str, str],
    subscription_id: UUID,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, any]:
    auth = azi.Auth(
        client_id=creds["client_id"],
        tenant_id=creds["tenant_id"],
        client_secret=creds["client_secret"],
    )
    blobs: Blobs = Blobs(
        container_name="testcontainer",
        auth=auth,
        subscription=subscription_id,
    ).aggregate_manifest_details(
        start_date=start_date,
        end_date=end_date,
    )
    tasks_id: list[UUID] = []
    for blob in blobs.collected_blob_data:
        task = process_blob.delay(
            creds=creds,
            subscription_id=subscription_id,
            blob_info=blob.model_dump(),
        )
        tasks_id.append(task.id)
    return {
        "subscription": blobs.subscription.display_name,
        "total_blobs": len(blobs.collected_blob_data),
        "tasks_id": tasks_id,
    }


@shared_task(name="nilakandi.tasks.process_blob")
@with_sub_name
def process_blob(
    creds: dict[str, str],
    subscription_id: UUID,
    blob_info: dict,
) -> dict[str, any]:
    blobs = Blobs(
        container_name="testcontainer",
        auth=creds,
        subscription=subscription_id,
    )
    blobs.collected_blob_data = [BlobsInfo(**blob_info)]
    blobs.import_blobs_from_manifest()
    return blobs.total_imported
