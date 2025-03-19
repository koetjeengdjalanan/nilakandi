import calendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
