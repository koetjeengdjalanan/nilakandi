import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional, Union
from uuid import UUID

import pandas as pd
from azure.storage.blob import BlobClient, BlobServiceClient, ExponentialRetry
from caseutil import to_snake
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from numpy import nan
from psycopg2.extras import DateTimeTZRange

from nilakandi.azure.models import BlobsInfo
from nilakandi.helper.azure_api import Auth
from nilakandi.models import ExportHistory as ExportHistoryModel
from nilakandi.models import ExportReport
from nilakandi.models import Subscription as SubscriptionModel


class Blobs:
    """
    Blobs class for Azure Blob Storage operations and data import into databases.

    This class provides functionality to interact with Azure Blob Storage, retrieve blob metadata,
    read manifest files, and import CSV data from blobs into a database. It handles data
    transformation, validation, and bulk database operations.

    Attributes:
        tobe_processed (int): Counter for blobs waiting to be processed.
        total_imported (int): Counter for total records successfully imported.
        collected_blob_data (list[BlobsInfo]): Collection of blob metadata information.

    Example:
        >>> auth = Auth(...)
        >>> subscription_id = UUID('...')
        >>> blobs = Blobs('container-name', auth, subscription_id)
        >>> blobs.aggregate_manifest_details(start_date=datetime(2023, 1, 1))
        >>> blobs.import_blobs_from_manifest()
        >>> blobs.aggregate_manifest_details().import_blobs_from_manifest()

    Dependencies:
        - Azure SDK for Python (azure-storage-blob)
        - pandas for CSV processing
        - Django for database operations
        - BlobsInfo model for metadata structure
        - ExportHistoryModel and ExportReport models for database operations
    """

    tobe_processed: int = 0
    total_imported: int = 0
    collected_blob_data: list[BlobsInfo] = []

    def __init__(
        self,
        container_name: str,
        auth: Auth,
        subscription: Union[SubscriptionModel | UUID],
    ):
        retry = ExponentialRetry(initial_backoff=5, retry_total=15)
        self.container_name = container_name
        self.blob_service_client = BlobServiceClient(
            account_url="https://stanillakandi.blob.core.windows.net",
            credential=auth.credential,
            retry_policy=retry,
        )
        self.subscription: SubscriptionModel = (
            subscription
            if isinstance(subscription, SubscriptionModel)
            else SubscriptionModel.objects.get(subscription_id=subscription)
        )

    def __str__(self):
        return f"Instance of Blobs for container: {self.container_name}"

    def stored_details(self) -> list[dict[str, any]]:
        """
        Retrieves a list of stored details for blobs in the specified container.

        This method connects to the Azure Blob Storage container and retrieves
        metadata for all blobs within the container. Each blob's details are
        represented as a dictionary and added to the resulting list.

        Returns:
            list[dict[str, any]]: A list of dictionaries containing metadata
            for each blob in the container.
        """
        res: list[dict[str, any]] = []
        for _ in self.blob_service_client.get_container_client(
            container=self.container_name
        ).list_blobs():
            res.append(_.__dict__)
        return res

    def read_manifest(
        self, path: str, export_history_id: Union[UUID | ExportHistoryModel]
    ) -> dict[str, any]:
        """
        Reads a manifest file from Azure Blob Storage and returns its contents as a dictionary.

        Args:
            path (str): The path to the directory containing the manifest file.
            export_history_id (Union[UUID, ExportHistoryModel]): The export history identifier,
                which can be either a UUID or an instance of ExportHistoryModel.

        Returns:
            dict[str, any]: A dictionary containing the contents of the manifest file,
            with an additional key "export_history_id" representing the export history identifier.

        Raises:
            Exception: If there is an error while reading or parsing the manifest file.

        Logs:
            - Logs an error message if reading the manifest fails.
            - Logs a debug message with details about the manifest, including run ID,
                version, byte count, blob count, and data row count.
        """
        client = self.blob_service_client.get_blob_client(
            container=self.container_name,
            blob=f"{path.rstrip("/")}/manifest.json",
        )
        try:
            res: dict[str, any] = json.loads(
                client.download_blob(max_concurrency=1, encoding="UTF-8").readall()
            )
        except Exception as e:
            logging.getLogger("nilakandi.pull").error(
                f"Error reading manifest from {path}: {e}", exc_info=True
            )
            raise
        res["export_history_id"] = (
            str(export_history_id)
            if isinstance(export_history_id, UUID)
            else export_history_id.id
        )
        logging.getLogger("nilakandi.pull").debug(
            f"Manifest {res.get('runInfo').get('runId')}: ver={res.get('manifestVersion')}, byteCount={res.get('byteCount')}, blobCount={res.get('blobCount')}, rows={res.get('dataRowCount')}"
        )
        return res

    def gather_history(self) -> ExportHistoryModel:
        raise NotImplementedError()

    def aggregate_manifest_details(
        self,
        start_date: datetime = datetime(2020, 1, 1, tzinfo=timezone.utc),
        end_date: datetime = datetime.now(tz=timezone.utc),
    ) -> "Blobs":
        """
        Aggregates manifest details from export history blobs within a specified date range.

        This method retrieves and processes manifest details from export history blobs
        associated with the subscription. It filters blobs based on the provided date range,
        reads their manifest data, and appends the collected blob information to the
        `collected_blob_data` attribute.

        Args:
            start_date (datetime, optional): The start date for filtering export history blobs.
                If not provided, defaults to January 1, 2020, in UTC timezone.
            end_date (datetime, optional): The end date for filtering export history blobs.
                Defaults to the current datetime in UTC timezone.

        Returns:
            Blobs: The instance of the class with updated `collected_blob_data` containing
                the aggregated blob information.

        Raises:
            ValueError: If any required data is missing or invalid during processing.

        Notes:
            - The method assumes that `self.subscription.exporthistory_set.subOne.exporthistory_set`
                is a valid queryable object with a `filter` method.
            - The `read_manifest` method is expected to return a dictionary containing
                manifest details, including a "blobs" key with blob data.
            - The `BlobsInfo` class is used to structure the collected blob data.
        """
        export_history_blobs_path: list[tuple[str, UUID]] = list(
            self.subscription.exporthistory_set.filter(
                report_datetime_range__overlap=DateTimeTZRange(start_date, end_date)
            ).values_list("blobs_path", "id")
        )
        manifest_details: list[dict] = []
        for manifest in export_history_blobs_path:
            manifest_details.append(self.read_manifest(*manifest))
        for manifest in manifest_details:
            for _ in manifest.get("blobs"):
                self.collected_blob_data.append(
                    BlobsInfo(
                        exportHistoryId=UUID(manifest.get("export_history_id", None)),
                        **_,
                    )
                )
        return self

    def import_csv_to_database(
        self, blob_info: BlobsInfo, chunk_size: int = 10_000
    ) -> "Blobs":
        """
        Imports CSV data from Azure Blob Storage directly into the database.

        Args:
            blob_path (str): Path to the CSV blob in Azure Storage
            export_history_id (UUID): The ExportHistory ID to associate with these records
            chunk_size (int): Number of rows to process at once (default: 10000)

        Returns:
            int: Number of records imported
        """
        logging.getLogger("nilakandi.pull").info(
            f"Importing CSV from {blob_info.blob_name}"
        )

        # Get the blob client for the specified path
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name, blob=blob_info.blob_name
        )

        # Attempt to get ExportHistory
        try:
            export_history = ExportHistoryModel.objects.get(
                id=blob_info.export_history_id
            )
        except ExportHistoryModel.DoesNotExist:
            raise ValueError(
                f"ExportHistory with ID {blob_info.export_history_id} does not exist"
            )

        # Stream the blob directly to pandas using chunks
        for chunk in self._read_csv_in_chunks(blob_client, chunk_size, blob_info):
            records = self._process_chunk(chunk, export_history)
            records_imported = self._bulk_import_records(records)
            self.total_imported += records_imported

            # Log progress
            logging.getLogger("nilakandi.db").info(
                f"Imported {records_imported} records {self.subscription.display_name} from {blob_info.blob_name}"
            )

        return self

    def _read_csv_in_chunks(
        self, blob_client: BlobClient, chunk_size: int, blob_info: BlobsInfo
    ) -> Iterator[pd.DataFrame]:
        """
        Streams a CSV file from Azure Blob Storage and yields chunks as pandas DataFrames.

        Args:
            blob_client (BlobClient): The Azure Blob client for the CSV file
            chunk_size (int): Number of rows to include in each chunk

        Yields:
            Iterator[pd.DataFrame]: Chunks of the CSV file as pandas DataFrames
        """
        from hashlib import md5

        from caseutil import to_snake

        props = blob_client.get_blob_properties()
        if props.size == 0:
            logging.getLogger("nilakandi.pull").error(
                f"Blob {blob_client.blob_name} is empty", exc_info=True
            )
            raise ValueError(f"Blob {blob_client.blob_name} is empty")
        source_md5 = props.content_settings.content_md5

        hasher = md5()
        report_downloads_dir = os.path.join(
            os.getcwd(),
            settings.AZURE_REPORT_DOWNLOAD_DIR,
            f"{to_snake(self.subscription.display_name)}",
            f"{blob_info.blob_name}",
        )
        os.makedirs(report_downloads_dir, exist_ok=True)
        file_name = os.path.basename(blob_client.blob_name)
        file_path = os.path.join(report_downloads_dir, file_name)
        with open(file_path, "wb") as report_file:
            stream = blob_client.download_blob(max_concurrency=2)
            for chunk in stream.chunks():
                hasher.update(chunk)
                report_file.write(chunk)
        # res = io.StringIO()
        # stream = blob_client.download_blob(encoding="UTF-8", max_concurrency=2)
        # for chunk in stream.chunks():
        #     hashser.update(chunk)
        #     res.write(chunk.decode("utf-8"))

        downloaded_md5 = hasher.digest()
        if downloaded_md5 != source_md5:
            os.remove(file_path)
            logging.getLogger("nilakandi.pull").error(
                f"MD5 mismatch for blob {blob_client.blob_name}: {downloaded_md5} != {source_md5}",
                exc_info=True,
            )
            raise ValueError(
                f"MD5 mismatch for blob {blob_client.blob_name}: {downloaded_md5} != {source_md5}"
            )

        # res.seek(0)
        for chunk in pd.read_csv(file_path, chunksize=chunk_size, low_memory=False):
            yield chunk

    def _process_chunk(
        self, chunk: pd.DataFrame, export_history: ExportHistoryModel
    ) -> list[Dict[str, Any]]:
        """
        Processes a chunk of CSV data, converting field names from PascalCase to snake_case.

        Args:
            chunk (pd.DataFrame): Chunk of CSV data
            export_history (ExportHistoryModel): The ExportHistory object to associate with records

        Returns:
            list[Dict[str, Any]]: List of dictionaries ready for database insertion
        """
        # Convert column headers from PascalCase to snake_case
        chunk.columns = [to_snake(col) for col in chunk.columns]
        for col in [
            "date",
            "service_info_1",
            "service_info_2",
            "billing_period_start_date",
            "billing_period_end_date",
        ]:
            if col in chunk.columns:
                chunk[col] = pd.to_datetime(
                    chunk[col], errors="coerce", utc=True
                ).dt.strftime("%Y-%m-%d")

        chunk.replace({nan: None, "": None}, inplace=True)
        records = chunk.to_dict("records")
        for record in records:
            record["export_history"] = export_history
            record["subscription"] = self.subscription

            # Handle JSON fields
            if "additional_info" in record and (
                isinstance(record["additional_info"], str)
                or record["additional_info"] is None
            ):
                try:
                    record["additional_info"] = json.loads(record["additional_info"])
                except (json.JSONDecodeError, TypeError):
                    record["additional_info"] = {}

        return records

    def _bulk_import_records(self, records: list[Dict[str, Any]]) -> int:
        """
        Bulk imports records to the database with error handling.

        Args:
            records (list[Dict[str, Any]]): List of record dictionaries to import

        Returns:
            int: Number of records successfully imported
        """
        if not records:
            return 0

        # Use transaction to ensure atomicity
        with transaction.atomic():
            # Filter out fields that don't exist in the model
            model_fields = {field.name for field in ExportReport._meta.fields}

            # Create objects and bulk insert
            objects = []
            for record in records:
                # Filter the record to include only valid fields
                filtered_record = {k: v for k, v in record.items() if k in model_fields}

                try:
                    # Create the object but don't save it yet (for bulk_create)
                    obj = ExportReport(**filtered_record)
                    obj.full_clean(exclude=["id"])  # Validate but exclude the id field
                    objects.append(obj)
                except ValidationError as e:
                    logging.getLogger("nilakandi.db").warning(
                        f"Skipping invalid record: {e}"
                    )

            # Bulk create all valid objects
            ExportReport.objects.bulk_create(
                objects, batch_size=1000, ignore_conflicts=True
            )

            return len(objects)

    # [x]: DONE
    def import_blobs_from_manifest(
        self,
        manifest_path: Optional[str] = None,
        export_history_id: Optional[UUID] = None,
    ) -> "Blobs":
        """
        Imports blobs from a manifest file or export history ID into the database.

        This method processes blob metadata from a manifest file or an export history ID,
        validates the blob details, and imports the corresponding CSV data into the database.

        Args:
            manifest_path (Optional[str]): The file path to the manifest JSON file containing blob metadata.
            export_history_id (Optional[UUID]): The UUID of the export history record to retrieve blob metadata.

        Returns:
            Blobs: The current instance of the Blobs class after processing and importing the blobs.

        Raises:
            ValueError: If the export history ID is invalid or does not exist, or if no blobs are found in the manifest.
            Exception: If an error occurs during the import of a blob's CSV data.

        Notes:
            - If `manifest_path` is provided, the method reads the manifest file to retrieve blob metadata.
            - If `manifest_path` is not provided, the method uses the `collected_blob_data` attribute.
            - Only blobs with `.csv` extensions and valid metadata (byte count and data row count) are processed.
            - Logs success or error messages for each blob processed.
        """

        def one_of(manifest_path: str, export_history_id: UUID) -> list[BlobsInfo]:
            if (
                not isinstance(export_history_id, UUID)
                or not ExportHistoryModel.objects.filter(id=export_history_id).exists()
            ):
                raise ValueError(
                    f"ExportHistory ID must be a UUID when collected_blob_data is Not provided! {export_history_id=}"
                )
            res = []
            manifests = self.read_manifest(
                path=manifest_path, export_history_id=export_history_id
            ).get("blobs", [])
            if not manifests:
                error_msg = f"{self.subscription} No blobs found in manifest {manifest_path}: {manifests}"
                logging.getLogger("nilakandi.pull").error(error_msg, exc_info=True)
                raise ValueError(error_msg)
            for _ in manifests:
                res.append(BlobsInfo(exportHistoryId=export_history_id, **_))
            return res

        manifest_data = (
            self.collected_blob_data
            if self.collected_blob_data
            else one_of(
                manifest_path=manifest_path, export_history_id=export_history_id
            )
        )

        for blob_info in manifest_data:
            blob_details_challenge = all(
                [
                    blob_info.blob_name.endswith(".csv"),
                    blob_info.byte_count,
                    blob_info.data_row_count,
                ]
            )
            if blob_details_challenge:
                try:
                    self.import_csv_to_database(blob_info=blob_info)

                    logging.getLogger("nilakandi.db").info(
                        f"Successfully imported {self.total_imported} records from {self.subscription} - {'/'.join(blob_info.blob_name.split('/'))}"
                    )
                except Exception as e:
                    logging.getLogger("nilakandi.db").error(
                        f"Error for {self.subscription} importing {'/'.join(blob_info.blob_name.split('/'))}: {str(e)}"
                    )
                    raise

        return self
