"""Azure data collection and reporting tasks for the Nilakandi application.

This module contains Celery tasks for interacting with Azure services, collecting usage and cost data,
and generating reports. It provides a framework for scheduled and on-demand operations against
Azure resources, with error handling, retry mechanisms, and logging.

The module includes tasks for:
- Collecting Azure service usage data
- Retrieving marketplace purchase information
- Exporting cost data to blob storage
- Processing blob storage manifests and contents
- Generating various types of reports from collected data

Tasks use a decorator pattern to enhance logging and monitoring by including subscription
information in task metadata. Most data collection tasks support date ranges and can be
configured to skip existing data.

Each task is designed to be idempotent where possible and includes appropriate error handling
with retry logic for transient failures. Long-running operations are broken into smaller,
manageable units of work.

Requirements:
- Azure credentials with appropriate permissions
- Database models for storing subscription and service data
- Celery configuration for task execution and monitoring
"""

import logging
import os
from datetime import datetime
from uuid import UUID

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from dateutil.relativedelta import relativedelta
from django.conf import settings
from pydantic_core import ValidationError

from nilakandi.azure.api.costexport import ExportHistory, ExportOrCreate
from nilakandi.azure.api.services import Services
from nilakandi.azure.models import BlobsInfo
from nilakandi.helper import azure_api as azi
from nilakandi.helper.azure_blob import Blobs
from nilakandi.helper.miscellaneous import df_tohtml, yearly_list
from nilakandi.helper.report_source_select import pivoting_data
from nilakandi.models import ReportDataSourceEnum
from nilakandi.models import Subscription as SubscriptionsModel
from nilakandi.task_handler import NilakandiTaskHandler


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
            while services.res.next_link:
                nextUrl = services.res.next_link
                services.pull(uri=nextUrl).db_save()
        except Exception as e:
            logging.getLogger("nilakandi.pull").error(
                f"Error in grabbing services for subscription {subscription_id}: {e}",
                exc_info=True,
            )
        finally:
            continue
    return {
        "subscription_id": subscription_id,
        "subscription_name": SubscriptionsModel.objects.get(subscription_id=subscription_id).display_name,
        "period": (start_date, end_date),
        "count": SubscriptionsModel.objects.get(subscription_id=subscription_id).services_set.count(),
    }


@shared_task(name="nilakandi.tasks.grab_marketplaces")
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
        for i in range((end_date.year - start_date.year) * 12 + end_date.month - start_date.month + 1)
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
def export_costs_to_blob(
    bearer: str,
    subscription_id: UUID,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, any]]:
    """Export costs to a blob storage for a given subscription within a date range.

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
        end_of_month = datetime.combine(current + relativedelta(month=0, day=31), datetime.min.time())
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
        current = datetime.combine(end_of_month + relativedelta(days=1), datetime.min.time())
    return exports


@shared_task(
    name="nilakandi.tasks.grab_cost_export_history",
    bind=True,
    max_retries=5,
    default_retry_delay=60,
)
def grab_cost_export_history(
    self,
    bearer: str,
    subscription_id: UUID,
) -> dict[str, any]:
    """Grab cost export history for a specified subscription.

    This shared task fetches the cost export history using the ExportHistory client,
    saves it to the database, and returns the result. It will retry up to 5 times
    with a 60-second delay between retries if any exceptions occur.

    Parameters
    ----------
    self : Task
        The Celery task instance (automatically injected due to bind=True).
    bearer : str
        The bearer token used for authentication.
    subscription_id : UUID
        The UUID of the subscription to fetch cost export history for.

    Returns:
        dict[str, any]
            The result of the export history operation.

    Raises:
        Retry
            If an exception occurs during execution, the task will be retried.
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


@shared_task(name="nilakandi.tasks.grab_blobs", bind=True, max_retries=5, default_retry_delay=60)
def grab_blobs(
    self,
    creds: dict[str, str],
    subscription_id: UUID,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, any]:
    """Fetch and process blobs from an Azure storage container for a given date range.

    This method authenticates with Azure using the provided credentials, retrieves blob
    data for the specified subscription between the start and end dates, and then creates
    asynchronous tasks to process each blob individually.

    Args:
        self: Task, The Celery task instance.
        creds (dict[str, str]): Azure credentials containing client_id, tenant_id, and client_secret.
        subscription_id (UUID): The Azure subscription identifier.
        start_date (datetime): The start date for blob collection.
        end_date (datetime): The end date for blob collection.

    Returns:
        dict[str, any]: A dictionary containing:
            - subscription (str): The display name of the subscription.
            - total_blobs (int): The number of blobs collected.
            - tasks_id (list[UUID]): List of task IDs for the spawned processing tasks.

    Raises:
        Exception: On failure to fetch blobs, retries after 60 seconds.
    """
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
def process_blob(
    self,
    creds: dict[str, str],
    subscription_id: UUID,
    blob_info: dict,
) -> dict[str, any]:
    """Process a blob from Azure Blob Storage using provided credentials.

    This Celery task authenticates with Azure using the provided credentials,
    connects to the specified blob container, and imports blob data based on
    the provided manifest information.

    Args:
        self: Bound task instance.
        creds (dict[str, str]): Azure authentication credentials containing
            'client_id', 'tenant_id', and 'client_secret'.
        subscription_id (UUID): The Azure subscription ID.
        blob_info (dict): Information about the blob to process, must be
            compatible with the BlobsInfo class.

    Returns:
        dict[str, any]: Dictionary containing information about the imported blobs,
        typically the result of blobs.total_imported.

    Raises:
        SoftTimeLimitExceeded: When task execution time exceeds the soft time limit.
            Task will be retried after 60 seconds.
        Exception: For any other errors during blob processing.
            Task will be retried after 60 seconds.
    """
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
            f"Soft time limit exceeded for processing blob {blob_info['name']} "
            f"in subscription {subscription_id}. Retrying..."
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
    name="nilakandi.tasks.make_report", bind=True, max_retries=5, default_retry_delay=60, base=NilakandiTaskHandler
)
def make_report(
    self,
    report_type: str,
    decimal_count: int,
    start_date: datetime.date,
    end_date: datetime.date,
    subscription_id: UUID | str,
    source: str = "db",
    file_list: list[str] | list[list[str]] = [],
    save_to_cloud: bool = True,
) -> dict[str, any]:
    """Generate a report for given parameters and optionally save it to cloud storage.

    This Celery task creates reports based on subscription data, handling various report types,
    data sources, and processing options. Reports can be generated from database records or
    external files, and results are stored in the database as GeneratedReportsModel instances.

    Parameters
    ----------
    self : Task
        The Celery task instance.
    report_type : str
        The type of report to generate. Can be a specific type from ReportTypeEnum or any value
        which will generate all report types.
    decimal_count : int
        Number of decimal places to use in the generated report.
    start_date : datetime.date
        Start date for the report data (inclusive). Can be a date object, datetime, or string.
    end_date : datetime.date
        End date for the report data (inclusive). Can be a date object, datetime, or string.
    subscription_id : UUID | str
        The subscription identifier to filter data. If not found, reports for all subscriptions
        will be generated.
    source : str, default="db"
        Data source type, e.g., "db" for database or other values from ReportDataSourceEnum.
        Non-db sources require a file_list to be provided.
    file_list : list[str] | list[list[str]], default=[]
        List of files to use as data sources when not using the database.
        Can be direct paths or [container_name, blob_name] pairs for Azure storage.
    save_to_cloud : bool, default=True
        Whether to save the generated report to cloud storage.

    Returns:
        dict[str, any]
            A dictionary containing metadata about the generated report(s):
            - 'subscriptions': List of subscription names
            - 'report_type': The requested report type
            - 'time_range': Tuple of (start_date, end_date)

    Raises:
        NotImplementedError
            When a non-db source is specified without providing file_list.
        ValueError
            When no data is found for the specified parameters or date parsing fails.

    Notes:
        - Progress updates are sent throughout the task execution via self.update_state
        - Reports are stored in the database if the subscription exists
        - Temporary files are cleaned up after processing when using BYOF source
    """
    from django.core.cache import cache
    from pandas import DataFrame
    from psycopg2.extras import DateTimeTZRange

    from nilakandi.helper.report_generation import process_csv_file
    from nilakandi.helper.report_source_select import gather_data
    from nilakandi.models import GeneratedReports as GeneratedReportsModel
    from nilakandi.models import GenerationStatusEnum, ReportTypeEnum

    def ensure_date_object(date_val):
        """Convert various date formats to datetime.date object."""
        if isinstance(date_val, str):
            try:
                return datetime.fromisoformat(date_val).date()
            except ValueError:
                try:
                    return datetime.strptime(date_val, "%Y-%m-%d").date()
                except ValueError:
                    raise ValueError(f"Unable to parse date: {date_val}")
        elif hasattr(date_val, "date"):
            return date_val.date()
        elif hasattr(date_val, "year") and hasattr(date_val, "month") and hasattr(date_val, "day"):
            return date_val
        else:
            raise ValueError(f"Invalid date format: {date_val}")

    start_date = ensure_date_object(start_date)
    end_date = ensure_date_object(end_date)
    dt_range = DateTimeTZRange(
        datetime.combine(start_date, datetime.min.time()),
        datetime.combine(end_date, datetime.max.time()),
    )

    all_subs: bool = False

    try:
        if subscription_id == "all":
            all_subs = True
            subscriptions: list[SubscriptionsModel] = list(SubscriptionsModel.objects.all())
        else:
            subscription_id = UUID(subscription_id) if isinstance(subscription_id, str) else subscription_id
            if not isinstance(subscription_id, UUID):
                raise ValueError(f"Invalid subscription_id format: {subscription_id}")
            subscriptions: list[SubscriptionsModel] = [SubscriptionsModel.objects.get(subscription_id=subscription_id)]
    except (SubscriptionsModel.DoesNotExist, ValidationError, ValueError):
        all_subs = True
        subscriptions = list(SubscriptionsModel.objects.all())

    try:
        reports = [ReportTypeEnum(report_type).value]
    except ValueError:
        reports = ReportTypeEnum.all()

    multiple_reports: bool = bool(len(reports) > 1)
    meta_state = {
        "current": 0,
        "total": 0,
        "status": "Spooling Tasks...",
        "subscriptions": subscription_id,
        "report_type": report_type,
        "time_range": (start_date, end_date),
    }

    self.update_state(state="PROGRESS", meta=meta_state)

    res: list[tuple[str, DataFrame]] = []
    if len(file_list) > 0:
        from nilakandi.helper.miscellaneous import download_file_from_azure

        meta_state["total"] = len(file_list)
        meta_state["status"] = "Downloading Source CSV File..."
        self.update_state(state="PROGRESS", meta=meta_state)
        path_list = []
        for file in file_list:
            if isinstance(file, list):
                path_list.append(str(download_file_from_azure(blob_name=file[1], container_name=file[0])))
            else:
                path_list.append(file)
            meta_state["current"] = len(path_list)
            self.update_state(state="PROGRESS", meta=meta_state)
        file_list = path_list

    meta_state["status"] = "Reading Sources..."
    meta_state["current"] = 0
    self.update_state(state="PROGRESS", meta=meta_state)

    if source != ReportDataSourceEnum.DB.value and not file_list:
        raise NotImplementedError(f"Source '{source}' requires a file_list to be provided when not using 'db' source.")

    source_df: DataFrame = gather_data(
        report_type=reports if not multiple_reports else ReportTypeEnum.SUMMARY.value.lower(),
        start_date=start_date,
        end_date=end_date,
        subscriptions=subscriptions,
        source=source,
        file_list=file_list,
    )
    if source_df.empty:
        raise ValueError("No data found for the specified parameters. Please check your date range and subscriptions.")

    dt_range = DateTimeTZRange(
        datetime.combine(source_df.billing_period_start_date.min(), datetime.min.time()),
        datetime.combine(source_df.billing_period_end_date.max(), datetime.max.time()),
    )
    meta_state["time_range"] = (source_df.billing_period_start_date.min(), source_df.billing_period_end_date.max())

    subs_from_df = None
    if all_subs:
        subs_from_df = source_df.subscription_name.unique()
        subs_from_df = subs_from_df[subs_from_df != "Unassigned"]

    meta_state["status"] = "Generating Reports..."
    meta_state["total"] = (
        (
            (len(reports) - reports.count(ReportTypeEnum.SUMMARY.value))
            * len(subs_from_df if all_subs else subscriptions)
        )
        + 1
        if save_to_cloud
        else 0 + 1 if ReportTypeEnum.SUMMARY.value in reports else 0
    )
    self.update_state(state="PROGRESS", meta=meta_state)
    generation_list: list[UUID] = []

    for subscription in [sub.display_name for sub in subscriptions] if not all_subs else subs_from_df:
        for report in reports:
            try:
                exist_in_db: bool = SubscriptionsModel.objects.filter(display_name=subscription).exists()
                if exist_in_db:
                    generated_report = GeneratedReportsModel.objects.create(
                        data_source=source,
                        subscription=SubscriptionsModel.objects.get(display_name=subscription),
                        report_type=report.lower(),
                        report_data={},
                        status=GenerationStatusEnum.IN_PROGRESS.value,
                        time_range=dt_range,
                    )
                    generated_report.save()

                meta_state["status"] = f"Generating {report} report for {subscription}..."
                self.update_state(state="PROGRESS", meta=meta_state)
                page_title, data = pivoting_data(
                    report_type=report.lower(),
                    data=process_csv_file(
                        input_dataframes=source_df, report_type=report.lower(), subscription_name=subscription
                    ),
                    subscription_name=subscription,
                )
                res.append((page_title, data))
                if exist_in_db:
                    pivot = df_tohtml(df=data, decimal=decimal_count)
                    generated_report.status = GenerationStatusEnum.COMPLETED.value
                    generated_report.report_data = {
                        "pivot": pivot,
                        "page_title": page_title,
                    }
                    generated_report.save(update_fields=["status", "report_data"])
                    cache.set(
                        key=generated_report.id,
                        value={
                            "page_title": page_title,
                            "pivot": pivot,
                            "status": "finish",
                        },
                        timeout=86400,
                    )

                meta_state["current"] = len(res)
                self.update_state(state="PROGRESS", meta=meta_state)
                logging.getLogger("nilakandi.tasks").info(
                    (
                        f"{(meta_state['current'] / meta_state['total'] * 100 if meta_state['total'] else 0):.2f}% "
                        f"Generated {report} report for {subscription} from {start_date} to {end_date}"
                    )
                )
            except Exception as e:
                logging.getLogger("nilakandi.tasks").error(
                    f"Error generating {report} report for subscription {subscription}: {e}",
                    exc_info=True,
                )
                if exist_in_db:
                    generated_report.status = GenerationStatusEnum.FAILED.value
                    generated_report.report_data = {"error": str(e)}
                    generated_report.save(update_fields=["status", "report_data"])
            finally:
                if exist_in_db:
                    generation_list.append(generated_report.id if exist_in_db else None)
                continue
        if ReportTypeEnum.SUMMARY.value in reports:
            reports.remove(ReportTypeEnum.SUMMARY.value)

    if save_to_cloud:
        from nilakandi.helper.excel_handler import export_to_excel, save_as_blob

        logging.getLogger("nilakandi.tasks").info(f"Saving report to cloud storage for {len(res)} reports")
        meta_state["status"] = "Creating Excel File..."
        self.update_state(state="PROGRESS", meta=meta_state)
        excel_buffer = export_to_excel(inputs=res, decimal_count=decimal_count)
        save_as_blob(file=excel_buffer, blobs_destination="Nilakandi-Result/")

    if len(file_list) > 0 and not settings.DEBUG:
        for file in file_list:
            try:
                os.remove(file)
            except OSError as e:
                logging.getLogger("nilakandi.tasks").warning(f"Error removing file {file}: {e}", exc_info=True)
            finally:
                continue

    return {
        "subscriptions": [sub.display_name for sub in subscriptions],
        "report_type": report_type,
        "time_range": (start_date, end_date),
        "results": generation_list,
    }
