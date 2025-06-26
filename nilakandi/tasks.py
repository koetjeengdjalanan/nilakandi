import logging
from datetime import datetime
from functools import wraps
from uuid import UUID

from celery import current_task, shared_task
from celery.exceptions import SoftTimeLimitExceeded
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
                    f"Error adding subscription info to task: {e}", exc_info=True
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
                f"Error in grabbing services for subscription {subscription_id}: {e}",
                exc_info=True,
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
                f"Error in grabbing marketplaces for {sub.display_name} month {month}: {e}",
                exc_info=True,
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


@shared_task(
    name="nilakandi.tasks.grab_cost_export_history",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
)
@with_sub_name
def grab_cost_export_history(
    self,
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
    try:
        res = (
            ExportHistory(
                bearer_token=bearer,
                subscription=subscription_id,
            )
            .pull()
            .db_save()
        )
    except Exception as e:
        logging.getLogger("nilakandi.tasks").error(
            f"Error fetching cost export history for subscription {subscription_id}: {e}",
            exc_info=True,
        )
        raise self.retry(exc=e, countdown=60)
    return res.res


@shared_task(
    name="nilakandi.tasks.grab_blobs", bind=True, max_retries=5, default_retry_delay=60
)
@with_sub_name
def grab_blobs(
    self,
    creds: dict[str, str],
    subscription_id: UUID,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, any]:
    try:
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
    except Exception as e:
        logging.getLogger("nilakandi.tasks").error(
            f"Error fetching blobs for subscription {subscription_id}: {e}",
            exc_info=True,
        )
        raise self.retry(exc=e, countdown=60)
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


@shared_task(
    name="nilakandi.tasks.process_blob",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    acks_late=True,
)
@with_sub_name
def process_blob(
    self,
    creds: dict[str, str],
    subscription_id: UUID,
    blob_info: dict,
) -> dict[str, any]:
    try:
        auth = azi.Auth(
            client_id=creds["client_id"],
            tenant_id=creds["tenant_id"],
            client_secret=creds["client_secret"],
        )
        blobs = Blobs(
            container_name="testcontainer",
            auth=auth,
            subscription=subscription_id,
        )
        blobs.collected_blob_data = [BlobsInfo(**blob_info)]
        blobs.import_blobs_from_manifest()
    except SoftTimeLimitExceeded as e:
        logging.getLogger("nilakandi.tasks").warning(
            f"Soft time limit exceeded for processing blob {blob_info['name']} in subscription {subscription_id}. Retrying..."
        )
        raise self.retry(exc=e, countdown=60)
    except Exception as e:
        logging.getLogger("nilakandi.tasks").error(
            f"Error fetching blob for subscription {subscription_id}: {e}",
            exc_info=True,
        )
        raise self.retry(exc=e, countdown=60)
    return blobs.total_imported


@shared_task(
    name="nilakandi.tasks.make_report",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
)
def make_report(
    self,
    report_type: str,
    decimal_count: int,
    start_date: datetime.date,
    end_date: datetime.date,
    subscription_id: UUID,
    source: str = "db",
    file_list: list[str] = [],
) -> dict[str, any]:
    """
    Generate a report based on the specified parameters and update its status in the database.

    This method retrieves subscription data, updates the status of a generated report to 'IN_PROGRESS',
    then attempts to gather report data. If successful, it updates the report status to 'SUCCESS' and
    returns report metadata. If an error occurs, it logs the error, updates the report status to 'FAILED',
    and re-raises the exception.

    Parameters:
        report_type (str): The type of report to generate.
        decimal_count (int): Number of decimal places to use in numeric values.
        start_date (datetime.date): The start date for the report period.
        end_date (datetime.date): The end date for the report period.
        subscription_id (UUID): The unique identifier for the subscription.
        source (str, optional): Data source to use for report generation. Defaults to "db".

    Returns:
        dict[str, any]: A dictionary containing:
            - 'page_title': The title for the report.
            - 'time_range': A tuple of (start_date, end_date).

    Raises:
        Exception: Any exception that occurs during report generation is logged and re-raised.
    """
    from django.core.cache import cache

    from nilakandi.helper.report_source_select import gather_data
    from nilakandi.models import GeneratedReports as GeneratedReportsModel
    from nilakandi.models import GenerationStatusEnum

    subscription = SubscriptionsModel.objects.get(subscription_id=subscription_id)
    generated_report = GeneratedReportsModel.objects.get(id=self.request.id)
    generated_report.status = GenerationStatusEnum.IN_PROGRESS.value
    generated_report.save()
    try:
        page_title, pivot = gather_data(
            report_type=report_type,
            decimal_count=decimal_count,
            start_date=start_date,
            end_date=end_date,
            subscription=subscription,
            source=source,
            file_list=file_list,
        )
        logging.getLogger("nilakandi.tasks").info(
            f"Generated report for {subscription.display_name} from {start_date} to {end_date}"
        )
        generated_report.status = GenerationStatusEnum.COMPLETED.value
        generated_report.report_data = {
            "pivot": pivot,
            "page_title": page_title,
        }
        logging.getLogger("nilakandi.tasks").info(
            f"database updated for {subscription.display_name} report {self.request.id}"
        )
        generated_report.save()
        cache.set(
            key=self.request.id,
            value={"page_title": page_title, "pivot": pivot},
            timeout=86400,
        )
        return {
            "page_title": page_title,
            "time_range": (start_date, end_date),
        }
    except Exception as e:
        logging.getLogger("nilakandi.tasks").error(
            f"Error generating report for subscription {subscription_id}: {e}",
            exc_info=True,
        )
        generated_report.status = GenerationStatusEnum.FAILED.value
        generated_report.report_data = {"error": str(e)}
        generated_report.save()
        raise e
