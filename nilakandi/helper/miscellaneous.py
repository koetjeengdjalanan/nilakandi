import calendar
from datetime import datetime, timedelta
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


def yearly_list(
    start_date: datetime, end_date: datetime
) -> list[tuple[datetime, datetime]]:
    """Yearly list of dates between start_date and end_date.

    Args:
        start_date (datetime): Start Date to generate the list.
        end_date (datetime): End Date to generate the list.

    Raises:
        ValueError: End date should always be greater then start date. Except in the event of time travels has ben invented.

    Returns:
        list[tuple[datetime, datetime]]: List of yearly dates.
    """
    if end_date < start_date:
        raise ValueError(
            "End date should be greater than start date", (start_date, end_date)
        )
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
                datetime.combine(
                    start_date, datetime.min.time(), tzinfo=ZoneInfo(settings.TIME_ZONE)
                ),
                datetime.combine(
                    end_date, datetime.max.time(), tzinfo=ZoneInfo(settings.TIME_ZONE)
                ),
            )
        ]
    return dates


def getlastmonth():
    """currently used by sml procedure"""
    right_now = datetime.now()

    # first_day_current_month = dt(right_now.year, right_now.month, 1)

    if right_now.month == 1:
        previous_month = 12
        year = right_now.year - 1
    else:
        previous_month = right_now.month - 1
        year = right_now.year

    first_day_previous_month = datetime(year, previous_month, 1)

    last_day_previous_month = datetime(
        year, previous_month, calendar.monthrange(year, previous_month)[1]
    )

    return first_day_previous_month, last_day_previous_month


# def generate_date_range(start_date:datetime, end_date: datetime) -> Iterable[datetime]:


def df_tohtml(df: pd.DataFrame, decimal: int = 16) -> str:
    """
    Convert a pandas DataFrame to HTML string with formatting.

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
            grand_total_indices = data.index[
                data.index.get_level_values(0) == "Grand Total"
            ]
            for idx in grand_total_indices:
                classes.loc[idx] = classes.loc[idx].apply(lambda s: s + "fw-bold")
        # Append gray text class for cells with missing values or value "n/a".
        for r in data.index:
            for c in data.columns:
                if pd.isna(data.at[r, c]) or str(data.at[r, c]) == "n/a":
                    classes.at[r, c] += "fw-lighter text-body text-opacity-25"
        return classes

    styled = (
        df.style.format(
            lambda x: f"{x:,.{decimal}f}".rstrip("0").rstrip("."), na_rep="n/a"
        )
        .set_table_attributes(
            attributes='class="table table-striped table-hover report-table"'
        )
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
