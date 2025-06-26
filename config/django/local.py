# flake8: noqa
from azure.identity import ClientSecretCredential, TokenCachePersistenceOptions

from .base import *

INSTALLED_APPS.append("django_extensions")

SKIPPABLE_HTTP_ERROR: list[int] = [
    400,  # Bad Request
    401,  # Unauthorized
    403,  # Forbidden
    404,  # Not Found
    409,  # Conflict
    500,  # Internal Server Error
    501,  # Not Implemented
    504,  # Gateway Timeout
]
EARLIEST_DATA: str = (
    env("EARLIEST_DATA", default="20200101") if not DEBUG else "20250101"
)

STORAGES["azures-storages"] = {
    "BACKEND": "storages.backends.azure_storage.AzureStorage",
    "OPTIONS": {
        "token_credential": ClientSecretCredential(
            tenant_id=env("AZURE_TENANT_ID"),
            client_id=env("AZURE_CLIENT_ID"),
            client_secret=env("AZURE_CLIENT_SECRET"),
            cache_persistence_options=TokenCachePersistenceOptions(
                allow_unencrypted_storage=True, name="nilakandi-azure-token"
            ),
        ),
        "account_name": env("AZURE_STORAGE_ACCOUNT_NAME", default="nilakandi"),
        "azure_container": env("AZURE_STORAGE_CONTAINER", default="nilakandi"),
    },
}

if DEBUG:
    import socket

    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = ["127.0.0.1"] + [
        (ip[:-1] + "1") for ip in socket.gethostbyname_ex(socket.gethostname())[2]
    ]
