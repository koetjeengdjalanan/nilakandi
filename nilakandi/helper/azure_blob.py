from azure.storage.blob import BlobServiceClient

from nilakandi.helper.azure_api import Auth


class BlobList:
    def __init__(self, container_name: str, auth: Auth):
        self.container_name = container_name
        self.blob_service_client = BlobServiceClient(
            account_url="https://stanillakandi.blob.core.windows.net",
            credential=auth.credentials,
        )

    def list_blobs(self):
        container_client = self.blob_service_client.get_container_client(
            self.container_name
        )
        blob_list = container_client.list_blobs()
        return blob_list

    def list_blobs_name(self):
        blob_list = self.list_blobs()
        blob_names = [blob.name for blob in blob_list]
        return blob_names

    def list_blobs_url(self):
        blob_list = self.list_blobs()
        blob_urls = [
            f"https://{self.blob_service_client.account_name}.blob.core.windows.net/{self.container_name}/{blob.name}"
            for blob in blob_list
        ]
        return blob_urls

    def list_blobs_properties(self):
        blob_list = self.list_blobs()
        blob_properties = [
            {
                "name": blob.name,
                "size": blob.size,
                "content_type": blob.content_settings.content_type,
            }
            for blob in blob_list
        ]
        return blob_properties

    def download_blob(self, blob_name, download_path):
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name, blob=blob_name
        )
        with open(download_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())

    def upload_blob(self, blob_name, upload_file_path):
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name, blob=blob_name
        )
        with open(upload_file_path, "rb") as upload_file:
            blob_client.upload_blob(upload_file, overwrite=True)

    def delete_blob(self, blob_name):
        blob_client = self.blob_service_client.get_blob_client(
            container=self.container_name, blob=blob_name
        )
        blob_client.delete_blob()

    def delete_container(self):
        container_client = self.blob_service_client.get_container_client(
            self.container_name
        )
        container_client.delete_container()

    def create_container(self):
        container_client = self.blob_service_client.get_container_client(
            self.container_name
        )
        container_client.create_container()
