import logging
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import requests
from dateutil.relativedelta import relativedelta
from django.db import transaction
from tenacity import (
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
)

from config.django.base import (
    AZURE_STORAGE_ACCOUNT_NAME,
    AZURE_STORAGE_CONTAINER,
    DEBUG,
    TIME_ZONE,
)
from nilakandi.helper.miscellaneous import wait_retry_after
from nilakandi.models import ExportHistory as ExportHistoryModel
from nilakandi.models import Subscription as SubscriptionsModel


class ExportOrCreate:
    """ExportOrCreate is a class that handles the creation and configuration of cost exports for an Azure subscription.

    Attributes:
        base_url (str): The base URL for the Azure Management API.
        subscription (SubscriptionsModel): The subscription model instance.
        schedules (tuple[datetime, datetime]): The start and end datetime for the schedule.
        end_date (datetime): The end date for the cost export.
        start_date (datetime): The start date for the cost export.
        headers (dict[str, str]): The headers for the HTTP request.
        payload (dict[str, any]): The payload for the cost export request.
        res (dict): The response from the export creation request.

    Methods:
        __init__(bearer_token: str, subscription: SubscriptionsModel | UUID, base_url: str = "https://management.azure.com", end_date: datetime = datetime.now(tz=ZoneInfo(TIME_ZONE)), start_date: datetime | None = None, schedule_start: datetime = datetime.now(tz=ZoneInfo(TIME_ZONE)), schedule_end: datetime = datetime.now(tz=ZoneInfo(TIME_ZONE)) + relativedelta(years=1)):
            Initializes the ExportOrCreate instance with the provided parameters.

        payload_config(*options, **kwargs) -> "ExportOrCreate":

        exec() -> "ExportOrCreate":

    Raises:
        ValueError: If the date range is more than 1 month or if the end date/schedules are before the start date/schedules.
    """

    def __init__(
        self,
        bearer_token: str,
        subscription: SubscriptionsModel | UUID,
        base_url: str = "https://management.azure.com",
        end_date: datetime = datetime.now(tz=ZoneInfo(TIME_ZONE)),
        start_date: datetime | None = None,
        schedule_start: datetime = datetime.now(tz=ZoneInfo(TIME_ZONE)),
        schedule_end: datetime = datetime.now(tz=ZoneInfo(TIME_ZONE))
        + relativedelta(years=1),
    ):
        date_diff = relativedelta(dt1=end_date, dt2=start_date)
        if start_date is not None and (date_diff.months > 1 or date_diff.days > 30):
            raise ValueError("Date range must be within 1 month")
        if start_date is not None and (
            end_date < start_date or schedule_end < schedule_start
        ):
            raise ValueError(
                "End date/schedules must be greater than start date/schedules"
            )
        self.base_url = base_url
        self.subscription: SubscriptionsModel = (
            subscription
            if isinstance(subscription, SubscriptionsModel)
            else SubscriptionsModel.objects.get(subscription_id=subscription)
        )
        self.schedules: tuple[datetime, datetime] = (
            schedule_start,
            schedule_end,
        )
        self.end_date: datetime = end_date
        self.start_date: datetime = (
            start_date
            if start_date is not None
            else datetime.combine(
                self.end_date.replace(day=1), self.end_date.min.time()
            )
        )
        self.headers: dict[str, str] = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "ClientType": "Nilakandi-NTT",
            "x-ms-command-name": "Nilakandi-CostExport",
        }
        self.payload_config()

    def payload_config(self, *options, **kwargs) -> "ExportOrCreate":
        """
        Generates and configures the payload for cost export.

        Args:
            *options: Variable length argument list for additional options.
            **kwargs: Arbitrary keyword arguments for additional configurations.

        Returns:
            ExportOrCreate: The instance of the class with the configured payload.

        Keyword Args:
            schedule (dict): Custom schedule configuration.
            deliveryInfo (dict): Custom delivery information.
            type (str): The type of cost export. Default is "ActualCost".
            granularity (str): The granularity of the data. Default is "Daily".
            dataOverwriteBehavior (str): Behavior for data overwrite. Default is "CreateNewReport".

        Options:
            "scheduled": If present, sets the schedule status to "Active".

        Payload Structure:
            properties:
                schedule:
                    status: "Inactive" or "Active"
                    recurrence: "Daily"
                    recurrencePeriod:
                        from: Start date-time in ISO 8601 format.
                        to: End date-time in ISO 8601 format.
                format: "Csv"
                deliveryInfo:
                    destination:
                        resourceId: Resource ID for the storage account.
                        container: Storage container name.
                        rootFolderPath: Root folder path in the storage account.
                definition:
                    type: "ActualCost"
                    timeframe: "Custom"
                    timePeriod:
                        from: Start date-time in ISO 8601 format.
                        to: End date-time in ISO 8601 format.
                    dataSet:
                        granularity: "Daily"
                        configuration:
                            dataVersion: None
                partitionData: True
                dataOverwriteBehavior: "CreateNewReport"
                exportDescription: Description of the export.
        """
        now: datetime = datetime.now()
        period = {
            "from": self.schedules[0].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "to": self.schedules[1].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        self.payload: dict[str, any] = {
            "properties": {
                "schedule": (
                    {
                        "status": (
                            "Inactive" if "scheduled" not in options else "Active"
                        ),
                        "recurrence": "Daily",
                        "recurrencePeriod": (
                            {
                                "from": datetime.combine(
                                    now, now.min.time(), tzinfo=ZoneInfo(TIME_ZONE)
                                ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                                "to": datetime.combine(
                                    now, now.max.time(), tzinfo=ZoneInfo(TIME_ZONE)
                                ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                            }
                            if ("scheduled" not in options)
                            else period
                        ),
                    }
                    if "schedule" not in kwargs
                    else kwargs["schedule"]
                ),
                "format": "Csv",
                "deliveryInfo": (
                    {
                        "destination": {
                            "resourceId": f"{self.subscription.id}/resourceGroups/Utilities/providers/Microsoft.Storage/storageAccounts/{AZURE_STORAGE_ACCOUNT_NAME}",
                            "container": AZURE_STORAGE_CONTAINER,
                            "rootFolderPath": str(self.subscription.subscription_id),
                        }
                    }
                    if "deliveryInfo" not in kwargs
                    else kwargs["deliveryInfo"]
                ),
                "definition": {
                    "type": "ActualCost" if "type" not in kwargs else kwargs["type"],
                    "timeframe": "Custom",
                    "timePeriod": {
                        "from": self.start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                        "to": self.end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    },
                    "dataSet": {
                        "granularity": (
                            "Daily"
                            if "granularity" not in kwargs
                            else kwargs["granularity"]
                        ),
                        "configuration": {"dataVersion": None},
                    },
                },
                "partitionData": True,
                "dataOverwriteBehavior": (
                    "CreateNewReport"
                    if "dataOverwriteBehavior" not in kwargs
                    else kwargs["dataOverwriteBehavior"]
                ),
                "exportDescription": (
                    "Nilakandi-DEV test export." if DEBUG else "Nilakandi Export"
                ),
            }
        }
        return self

    @retry(
        stop=stop_after_attempt(5),
        reraise=True,
        wait=wait_retry_after,
        retry=retry_if_exception(
            lambda e: isinstance(e, requests.HTTPError)
            and e.response.status_code != 404
        ),
        before_sleep=before_sleep_log(
            logging.getLogger("nilakandi.pull"), logging.WARN
        ),
        after=after_log(logging.getLogger("nilakandi.pull"), logging.INFO),
    )
    def exec(self) -> "ExportOrCreate":
        """
        Executes the export creation process for the given subscription.

        This method sends a PUT request to the Azure Cost Management API to create
        an export for the specified subscription. If the request is successful, the
        response is stored in the `res` attribute and the method returns the current
        instance. If the request fails with a 404 status code, an error is logged.

        Returns:
            ExportOrCreate: The current instance with the response data.

        Raises:
            requests.HTTPError: If the request fails with an HTTP error other than 404.
        """
        logging.getLogger("nilakandi.pull").info(
            f"Creating export for {self.subscription} - {self.start_date} to {self.end_date}"
        )
        try:
            reqRes = requests.put(
                url=f"{self.base_url}{self.subscription.id}/providers/Microsoft.CostManagement/exports/Nilakandi-NTT-Export",
                params={"api-version": "2023-07-01-preview"},
                headers=self.headers,
                json=self.payload,
            )
            reqRes.raise_for_status()
            self.res = reqRes.json().copy()
            return self
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logging.getLogger("nilakandi.pull").error(
                    f"Data not found for {self.subscription} (HTTP 404)"
                )
            raise


class ExportHistory:
    """ExportHistory class for managing export history data from Azure API.
    ref: https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2023-07-01-preview&tabs=HTTP#exportrunhistorygetbysubscription

    Attributes:
        headers (dict[str, str]): HTTP headers for the API requests.
        url (str): The URL for the Azure API endpoint.
        subscription (SubscriptionsModel): The subscription model instance.

    Methods:
        __init__(bearer_token: str, subscription: SubscriptionsModel | UUID, base_url: str = "https://management.azure.com", export_name: str = "Nilakandi-NTT-Export"):
            Initializes the ExportHistory instance with the provided parameters.

        pull() -> "ExportHistory":

        db_save() -> "ExportHistory":
    """

    def __init__(
        self,
        bearer_token: str,
        subscription: SubscriptionsModel | UUID,
        base_url: str = "https://management.azure.com",
        export_name: str = "Nilakandi-NTT-Export",
    ):
        self.headers: dict[str, str] = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "ClientType": "Nilakandi-NTT",
            "x-ms-command-name": "Nilakandi-CostExport",
        }
        self.url = f"{base_url}{subscription.id}/providers/Microsoft.CostManagement/exports/{export_name}/runHistory"
        self.subscription: SubscriptionsModel = (
            subscription
            if isinstance(subscription, SubscriptionsModel)
            else SubscriptionsModel.objects.get(subscription_id=subscription)
        )

    @retry(
        stop=stop_after_attempt(5),
        reraise=True,
        wait=wait_retry_after,
        retry=retry_if_exception(
            lambda e: isinstance(e, requests.HTTPError)
            and e.response.status_code != 404
        ),
        before_sleep=before_sleep_log(
            logging.getLogger("nilakandi.pull"), logging.WARN
        ),
        after=after_log(logging.getLogger("nilakandi.pull"), logging.INFO),
    )
    def pull(self) -> "ExportHistory":
        """
        Pulls data for the specified subscription from the Azure API.

        This method sends a GET request to the Azure API using the provided URL,
        headers, and API version. It logs the action and raises an exception if
        the request fails. The response is stored in the `res` attribute as a
        dictionary.

        Returns:
            ExportHistory: The instance of the class with the response data.
        """
        logging.getLogger("nilakandi.pull").info(
            f"Pulling history for {self.subscription}"
        )
        try:
            reqRes = requests.get(
                url=self.url,
                params={"api-version": "2023-07-01-preview"},
                headers=self.headers,
            )
            reqRes.raise_for_status()  # Raises HTTPError for non-2xx responses
            self.res = reqRes.json().copy()
            return self
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logging.getLogger("nilakandi.pull").error(
                    f"Data not found for {self.subscription} (HTTP 404)"
                )
            raise

    def db_save(self) -> "ExportHistory":
        """
        Saves the export history data to the database.

        This method processes the response data (`self.res`) and saves it to the database
        as instances of `ExportHistoryModel`. It performs the following steps:
        1. Checks if the response data is valid and contains the required "value" key.
        2. Iterates over the response data, extracting relevant properties and creating
            `ExportHistoryModel` instances.
        3. Uses a database transaction to bulk create the `ExportHistoryModel` instances.
        4. Logs the progress and results of the save operation.

        Raises:
            ValueError: If the response data is empty or does not contain the "value" key.
            Exception: If there is an error during the database save operation.

        Returns:
            ExportHistory: The instance of the class on which this method is called.
        """
        if not self.res or "value" not in self.res:
            logging.getLogger("django.db.save").warning("No data to save")
            raise ValueError("No data to save")
        data: list[ExportHistoryModel] = []
        for res in self.res.get("value", []):
            properties = res.get("properties", {})
            run_settings = properties.get("runSettings", {})
            definition = run_settings.get("definition", {})
            time_period = definition.get("timePeriod", {})
            entry = ExportHistoryModel(
                id=res.get("name"),
                subscription=self.subscription,
                exec_string=res.get("id"),
                blobs_path=properties.get("manifestFile"),
                exec_type=properties.get("executionType"),
                exec_status=properties.get("status"),
                submitted=(
                    datetime.fromisoformat(properties["submittedTime"])
                    if "submittedTime" in properties
                    else None
                ),
                proc_start_time=(
                    datetime.fromisoformat(properties["processingStartTime"])
                    if properties.get("processingStartTime")
                    else None
                ),
                proc_end_time=(
                    datetime.fromisoformat(properties["processingEndTime"])
                    if properties.get("processingEndTime")
                    else None
                ),
                report_datetime_range=(
                    (
                        datetime.fromisoformat(time_period["from"]),
                        datetime.fromisoformat(time_period["to"]),
                    )
                    if "from" in time_period and "to" in time_period
                    else None
                ),
                run_settings=run_settings,
            )
            data.append(entry)
            logging.getLogger("django.db.save").info(
                f"Prepared entry: {entry.id} - {entry.exec_status}"
            )
        try:
            with transaction.atomic():
                created_objs = ExportHistoryModel.objects.bulk_create(
                    data, batch_size=500
                )
            for obj in created_objs:
                logging.getLogger("django.db.save").debug(
                    f"Inserted into DB: {obj.id} - {obj.exec_status}"
                )
            logging.getLogger("django.db.save").info(
                f"Total records inserted: {len(created_objs)}"
            )
        except Exception as e:
            logging.getLogger("django.db.save").error(f"Failed to save data: {e}")
            raise
        return self
