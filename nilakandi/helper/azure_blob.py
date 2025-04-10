import io
import json
import logging
from typing import Any, Dict, Iterator, Optional, Union
from uuid import UUID

import pandas as pd
from azure.storage.blob import BlobClient, BlobServiceClient
from caseutil import to_snake
from django.core.exceptions import ValidationError
from django.db import transaction
from numpy import nan

from nilakandi.azure.models import BlobsInfo
from nilakandi.helper.azure_api import Auth
from nilakandi.models import ExportHistory as ExportHistoryModel
from nilakandi.models import ExportReport
from nilakandi.models import Subscription as SubscriptionModel


class Blobs:
    tobe_processed: int = 0
    total_imported: int = 0
    collected_blob_data: list[BlobsInfo] = []

    def __init__(
        self,
        container_name: str,
        auth: Auth,
        subscription: Union[SubscriptionModel | UUID],
    ):
        self.container_name = container_name
        self.blob_service_client = BlobServiceClient(
            account_url="https://stanillakandi.blob.core.windows.net",
            credential=auth.credential,
        )
        self.subscription: SubscriptionModel = (
            subscription
            if isinstance(subscription, SubscriptionModel)
            else SubscriptionModel.objects.get(subscription_id=subscription)
        )

    def __str__(self):
        return f"Instance of Blobs for container: {self.container_name}"

    def stored_details(self) -> list[dict[str, any]]:
        res: list[dict[str, any]] = []
        for _ in self.blob_service_client.get_container_client(
            container=self.container_name
        ).list_blobs():
            res.append(_.__dict__)
        return res

    def read_manifest(
        self, path: str, export_history_id: Union[UUID | ExportHistoryModel]
    ) -> dict[str, any]:
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
                f"Error reading manifest from {path}: {e}"
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

    def aggregate_manifest_details(self) -> "Blobs":
        """
        Aggregates manifest details from the export history of a subscription and collects blob data.

        This method retrieves the export history blobs' paths and IDs associated with the subscription,
        reads the manifest details for each blob, and appends the collected blob data to the `collected_blob_data` attribute.

        Returns:
            Blobs: The current instance of the class with updated `collected_blob_data`.

        Raises:
            KeyError: If the manifest does not contain the expected keys.
            ValueError: If the `export_history_id` in the manifest is invalid.

        Notes:
            - The `read_manifest` method is expected to process each blob path and return a dictionary
                containing the manifest details, including a list of blobs and an `export_history_id`.
            - The `BlobsInfo` class is used to structure the collected blob data.
        """
        export_history_blobs_path: list[tuple[str, UUID]] = list(
            self.subscription.exporthistory_set.values_list("blobs_path", "id")
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
        for chunk in self._read_csv_in_chunks(blob_client, chunk_size):
            records = self._process_chunk(chunk, export_history)
            records_imported = self._bulk_import_records(records)
            self.total_imported += records_imported

            # Log progress
            logging.getLogger("nilakandi.db").info(
                f"Imported {records_imported} records from {blob_info.blob_name}"
            )

        return self

    def _read_csv_in_chunks(
        self, blob_client: BlobClient, chunk_size: int
    ) -> Iterator[pd.DataFrame]:
        """
        Streams a CSV file from Azure Blob Storage and yields chunks as pandas DataFrames.

        Args:
            blob_client (BlobClient): The Azure Blob client for the CSV file
            chunk_size (int): Number of rows to include in each chunk

        Yields:
            Iterator[pd.DataFrame]: Chunks of the CSV file as pandas DataFrames
        """
        # Download the blob and stream it to pandas
        stream = io.StringIO(blob_client.download_blob().readall().decode("utf-8"))

        # Read the CSV in chunks
        for chunk in pd.read_csv(stream, chunksize=chunk_size):
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
                    "ExportHistory ID must be a UUID when manifest_path is provided"
                )
            res = []
            manifests = self.read_manifest(
                path=manifest_path, export_history_id=export_history_id
            ).get("blobs", [])
            if not manifests:
                error_msg = f"No blobs found in manifest {manifest_path}: {manifests}"
                logging.getLogger("nilakandi.pull").error(error_msg)
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

        return self
