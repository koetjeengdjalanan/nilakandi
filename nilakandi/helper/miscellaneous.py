"""Miscellaneous helper functions."""

import calendar
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import tenacity
from django.conf import settings


def wait_retry_after(retry_state: tenacity.RetryCallState) -> int:
    """Wait for the Retry-After time from the response headers.

    Args:
        retry_state (tenacity.RetryCallState): Retry state object.

    Returns:
        int: time to wait in seconds.
    """
    try:
        response = retry_state.outcome.result()
        if response is not None and "Retry-After" in response.headers:
            return int(response.headers["Retry-After"])
    except Exception:
        pass
    return 20


def yearly_list(start_date: datetime, end_date: datetime) -> list[tuple[datetime, datetime]]:
    """Yearly list of dates between start_date and end_date.

    Args:
        start_date (datetime): Start Date to generate the list.
        end_date (datetime): End Date to generate the list.

    Raises:
        ValueError: End date should always be greater then start date.
                    Except in the event of time travels has ben invented.

    Returns:
        list[tuple[datetime, datetime]]: List of yearly dates.
    """
    if end_date < start_date:
        raise ValueError("End date should be greater than start date", (start_date, end_date))
    if end_date - start_date > timedelta(days=364):
        dates = [
            (
                datetime.combine(
                    start_date + timedelta(days=364 * i),
                    datetime.min.time(),
                    tzinfo=ZoneInfo(settings.TIME_ZONE),
                ),
                datetime.combine(
                    start_date + timedelta(days=364 * (i + 1)),
                    datetime.max.time(),
                    tzinfo=ZoneInfo(settings.TIME_ZONE),
                ),
            )
            for i in range((end_date - start_date).days // 364)
        ]
        if dates[-1][1] < end_date:
            dates.append(
                (
                    dates[-1][1] + timedelta(seconds=1),
                    datetime.combine(
                        end_date,
                        datetime.max.time(),
                        tzinfo=ZoneInfo(settings.TIME_ZONE),
                    ),
                )
            )
    else:
        dates = [
            (
                datetime.combine(start_date, datetime.min.time(), tzinfo=ZoneInfo(settings.TIME_ZONE)),
                datetime.combine(end_date, datetime.max.time(), tzinfo=ZoneInfo(settings.TIME_ZONE)),
            )
        ]
    return dates


def getlastmonth():
    """Currently used by sml procedure."""
    right_now = datetime.now()

    # first_day_current_month = dt(right_now.year, right_now.month, 1)

    if right_now.month == 1:
        previous_month = 12
        year = right_now.year - 1
    else:
        previous_month = right_now.month - 1
        year = right_now.year

    first_day_previous_month = datetime(year, previous_month, 1)

    last_day_previous_month = datetime(year, previous_month, calendar.monthrange(year, previous_month)[1])

    return first_day_previous_month, last_day_previous_month


# def generate_date_range(start_date:datetime, end_date: datetime) -> Iterable[datetime]:


def df_tohtml(df: pd.DataFrame, decimal: int = 16) -> str:
    """Convert a pandas DataFrame to HTML string with formatting.

    This function converts a pandas DataFrame to an HTML table with specific formatting:
    - Adds CSS classes for styling ('table table-striped')
    - Formats float numbers to remove trailing zeros
    - Represents missing values as 'n/a'
    - Returns a simple message if the DataFrame is empty

    Args:
        df (pd.DataFrame): The pandas DataFrame to convert to HTML.
        decimal (int, optional): Number of decimal places to format. Defaults to 16.

    Returns:
        str: HTML representation of the DataFrame or a message if the DataFrame is empty.
    """
    if df.empty:
        return "<pre>No Data</pre>"

    def highlight_total_classes(data):
        # Build a DataFrame of empty strings for CSS classes.
        classes = pd.DataFrame("", index=data.index, columns=data.columns)
        # Append bold class to the last column if its header is 'Grand Total'
        if "Grand Total" in data.columns[-1]:
            classes.iloc[:-1, -1] += "fw-bold"
        # Append bold class to the entire row where the index is 'Grand Total'
        if "Grand Total" in data.index.get_level_values(0):
            grand_total_indices = data.index[data.index.get_level_values(0) == "Grand Total"]
            for idx in grand_total_indices:
                classes.loc[idx] = classes.loc[idx].apply(lambda s: s + "fw-bold")
        # Append gray text class for cells with missing values or value "n/a".
        for r in data.index:
            for c in data.columns:
                if pd.isna(data.at[r, c]) or str(data.at[r, c]) == "n/a":
                    classes.at[r, c] += "fw-lighter text-body text-opacity-25"
        return classes

    styled = (
        df.style.format(lambda x: f"{x:,.{decimal}f}".rstrip("0").rstrip("."), na_rep="n/a")
        .set_table_attributes(attributes='class="table table-striped table-hover report-table"')
        .set_table_styles(
            table_styles=[
                {
                    "selector": "thead",
                    "props": [("position", "sticky"), ("top", "0"), ("z-index", "1")],
                },
                # {"selector": "th", "props": [("white-space", "nowrap")]},
                # {"selector": "td", "props": [("text-align", "right")]},
            ]
        )
        .set_td_classes(highlight_total_classes(df))
    )
    res = styled.to_html()
    return res


def use_temporary_file_upload_handler(func):
    """Decorator that forces Django to use TemporaryFileUploadHandler for file uploads.

    This decorator replaces the default upload handlers in the request with a single
    TemporaryFileUploadHandler, which stores uploaded files directly to disk rather
    than keeping them in memory. This is useful for handling large file uploads that
    might exceed memory limits.

    Args:
        func: The view function to decorate.

    Returns:
        The wrapped function that will use TemporaryFileUploadHandler for all file uploads.

    Example:
        @use_temporary_file_upload_handler
        def upload_view(request):
            # All file uploads in this view will be handled by TemporaryFileUploadHandler
            # and stored on disk instead of in memory
            ...
    """
    from functools import wraps

    from django.core.files.uploadhandler import TemporaryFileUploadHandler

    @wraps(func)
    def _wrap_api(request, *args, **kwargs):
        request.upload_handlers = [TemporaryFileUploadHandler(request=request)]
        return func(request, *args, **kwargs)

    return _wrap_api


def download_file_from_azure(blob_name: str, container_name: str) -> Path:
    """Download a file from Azure Blob Storage.

    Args:
        blob_name (str): The name of the blob to download.
        container_name (str): The name of the container where the blob is stored.

    Returns:
        str: The local path to the downloaded file.
    """
    from azure.storage.blob import BlobServiceClient, ExponentialRetry

    from nilakandi.helper.azure_api import Auth

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=1, min=4, max=60),
        retry=tenacity.retry_if_exception_type((Exception,)),
        reraise=True,
    )
    def _download_with_retry():
        temp_file_path = file_path.with_suffix(file_path.suffix + ".tmp")
        logging.getLogger("nilakandi.pull").info(f"Downloading {blob_name} to {temp_file_path}")

        try:
            blob_properties = blob_client.get_blob_properties()
            blob_size = blob_properties.size

            with open(temp_file_path, "wb") as target_file:
                download_stream = blob_client.download_blob(
                    validate_content=True,
                    max_concurrency=8,
                    timeout=None,
                )

                downloaded_bytes = 0

                for chunk in download_stream.chunks():
                    target_file.write(chunk)
                    downloaded_bytes += len(chunk)

                    if blob_size > 100 * 1024 * 1024 and downloaded_bytes % (50 * 1024 * 1024) == 0:
                        progress_percent = (downloaded_bytes / blob_size) * 100
                        print(f"Downloaded {progress_percent:.1f}% of {blob_name}")

            if temp_file_path.stat().st_size != blob_size:
                raise ValueError(
                    f"Downloaded file size mismatch: expected {blob_size}, got {temp_file_path.stat().st_size}"
                )

            temp_file_path.rename(file_path)

        except Exception as e:

            if temp_file_path.exists():
                temp_file_path.unlink()
            raise e

    file_path = Path(settings.FILE_UPLOAD_TEMP_DIR).joinpath(blob_name.replace("/", "_"))
    if file_path.exists(follow_symlinks=True):
        logging.getLogger("nilakandi.pull").info(f"File {file_path} already exists, skipping download.")
        return file_path

    auth = Auth(
        client_id=settings.AZURE_CLIENT_ID,
        tenant_id=settings.AZURE_TENANT_ID,
        client_secret=settings.AZURE_CLIENT_SECRET,
    )

    enhanced_retry_policy = ExponentialRetry(
        initial_backoff=2,
        retry_total=20,
        max_backoff=120,
        increment_base=1.5,
        retry_on_status_codes=[429, 500, 502, 503, 504],
    )

    service_client = BlobServiceClient(
        account_url="https://stanillakandi.blob.core.windows.net",
        credential=auth.credential,
        connection_timeout=60,
        read_timeout=None,
        retry_policy=enhanced_retry_policy,
    )

    blob_client = service_client.get_blob_client(container=container_name, blob=blob_name)

    _download_with_retry()

    return file_path
