"""Azure Cost Report Generation Module.

This module provides functionality to generate various types of Azure cost reports
by processing data from different sources, including CSV files, database records,
and Azure storage. It supports multiple report types: summary, services, marketplaces,
and virtual machines.

Key Components:
--------------
1. Data Source Functions:
    - byof_source_switch: Processes CSV files from local filesystem
    - grab_from_azure: Retrieves and processes data from Azure storage
    - db_source_switch: Retrieves and processes data from the database

2. Data Processing Functions:
    - process_csv_file: Processes data based on report type requirements
    - _min_max_dates: Helper to determine date ranges for queries

3. Report Generation Functions:
    - summary: Creates subscription cost summary pivot tables
    - services: Creates service-based cost reports
    - marketplaces: Creates marketplace-specific cost reports
    - virtual_machines: Creates detailed VM cost and metadata reports

Configuration:
-------------
COLUMN_STACKS: Defines required columns for each report type
pandas_read_csv_args: Configuration for pandas CSV reading operations

Dependencies:
-------------
- pandas: For data processing and pivot table generation
- Django ORM: For database access
- Azure Storage: For retrieving cost data files

Usage:
Typically used by views or tasks to generate reports based on user requests.
The workflow generally involves:
1. Retrieving raw data from a source
2. Processing the data with report-specific logic
3. Generating a formatted pivot table for display or export

Note:
This module is designed to work with Azure Cost Management exported data
in specific formats. Data validation and error handling are built in to
ensure consistency across different data sources.
"""

import logging
from datetime import date
from typing import Dict, Union

import pandas as pd
from caseutil import to_camel
from django.db.models import Max, Min, Sum
from django.db.models.functions import TruncMonth

from nilakandi.models import ExportReport as ExportReportModel
from nilakandi.models import Subscription as SubscriptionModel

COLUMN_STACKS: Dict[str, tuple[str]] = {
    "summary": [
        "subscription_name",
        "month",
        "publisher_type",
        "billing_period_end_date",
        "billing_period_start_date",
        "total_cost",
    ],
    "services": [
        "meter_category",
        "meter_sub_category",
        "meter_name",
        "month",
        "total_cost",
        "billing_period_end_date",
        "billing_period_start_date",
    ],
    "marketplaces": [
        "publisher_name",
        "plan_name",
        "month",
        "total_cost",
        "billing_period_end_date",
        "billing_period_start_date",
    ],
    "virtualmachines": [
        "resource_name",
        "resource_group",
        "tags",
        "meter_category",
        "resource_id",
        "billing_period_end_date",
        "billing_period_start_date",
        "total_cost",
        "vm_sku",
    ],
}

pandas_read_csv_args = {
    "parse_dates": [
        "Date",
        "BillingPeriodStartDate",
        "BillingPeriodEndDate",
    ],
    "date_format": "%m/%d/%Y",
    "cache_dates": True,
    "engine": "c",
    "encoding": "utf-8",
    "quotechar": '"',
    "on_bad_lines": "error",
    "low_memory": False,
}


def _min_max_dates(
    start_date: date = None,
    end_date: date = None,
) -> tuple[date, date]:
    dates = ExportReportModel.objects.aggregate(
        min_date=Min("billing_period_start_date"),
        max_date=Max("billing_period_end_date"),
    )
    start_date = start_date or dates["min_date"]
    end_date = end_date or dates["max_date"]
    return start_date, end_date


# [x]: Refactor this function to be handle multiple subscription and only return the raw dataframe
def byof_source_switch(file_paths: list[str]) -> pd.DataFrame:
    """Reads CSV files from the provided file paths and combines them into a single DataFrame.

    Args:
        file_paths (list[str]): A list of file paths to CSV files to be read.
                               If the first element is itself a list, that list will be used instead.

    Returns:
        pd.DataFrame: A concatenated DataFrame containing data from all CSV files.
                     If no files were successfully read, returns an empty DataFrame.

    Raises:
        ValueError: If any file does not have a .csv extension.
        Exception: If there's an error reading any of the CSV files.

    Notes:
        - Column names in the resulting DataFrame are converted to snake_case.
        - The function uses the pandas_read_csv_args global variable when reading CSV files.
    """
    from io import StringIO

    from caseutil import to_snake

    res = []
    files = file_paths[0] if isinstance(file_paths[0], list) else file_paths
    for file in files:
        if not file.endswith(".csv"):
            raise ValueError(f"Invalid file format: {file}. Only CSV files are allowed.")
        with open(file, "rb") as raw:
            try:
                df = pd.read_csv(
                    StringIO(raw.read().decode("utf-8")),
                    **pandas_read_csv_args,
                )
            except Exception as e:
                logging.getLogger("nilakandi.tasks").error(f"Error in reading file {file}: {e}")
                raise
            if not df.empty:
                df.columns = [to_snake(col) for col in df.columns]
                res.append(df)

    return pd.concat(res) if len(res) > 0 else pd.DataFrame()


def process_csv_file(
    input_dataframes: pd.DataFrame,
    report_type: str,
    subscription_name: str | None = None,
) -> pd.DataFrame:
    """Process a CSV file for report generation based on the specified report type.

    This function takes a pandas DataFrame containing cost data and processes it according to the
    specified report type. It performs data validation, filtering, and transformation operations
    to prepare the data for reporting.

    Parameters
    ----------
    input_dataframes : pd.DataFrame
        The pandas DataFrame containing the data to be processed. Previously accepted lists,
        but this usage is now deprecated.
    report_type : str
        The type of report to generate. Must be one of the types defined in COLUMN_STACKS.
        Supported types include 'summary', 'services', 'marketplaces', and 'virtualmachines'.
    subscription_name : str | None, optional
        The name of the subscription to filter by. Required for non-summary reports.
        Default is None.

    Returns:
    -------
    pd.DataFrame
        A processed DataFrame containing only the columns required for the specified report type,
        as defined in COLUMN_STACKS.

    Raises:
    ------
    ValueError
        If an invalid report type is provided, if subscription_name is missing for non-summary reports,
        or if required columns are missing.
    TypeError
        If input_dataframes is not a pandas DataFrame.
    KeyError
        If required columns are missing from the input DataFrame.

    Notes:
    -----
    The function performs different processing steps depending on the report_type:
    - 'summary': Basic validation only
    - 'services': Filters out unassigned meter categories
    - 'marketplaces': Filters for marketplace publisher types
    - 'virtualmachines': Filters for VM-related resources and extracts VM SKU information
    """
    import json

    if report_type not in COLUMN_STACKS:
        raise ValueError("Invalid report type provided")

    if not isinstance(input_dataframes, pd.DataFrame):
        raise TypeError(
            "Passing list to this function is deprecated. Input data must be a pandas DataFrame.",
            type(input_dataframes),
        )

    df_concated = input_dataframes.copy()
    if report_type != "summary":
        if not subscription_name or not isinstance(subscription_name, str):
            raise ValueError("Subscription name is required for non-summary reports.")
        df_concated = df_concated[df_concated.subscription_name.str.match(subscription_name, case=False, na=False)]

    if "cost_in_billing_currency" in df_concated.columns:
        df_concated.rename(columns={"cost_in_billing_currency": "total_cost"}, inplace=True)

    for col in ("billing_period_start_date", "billing_period_end_date"):
        if col not in df_concated.columns:
            raise KeyError(f"{col} column missing in data")
    df_concated = df_concated[
        df_concated["billing_period_start_date"].notnull() & df_concated["billing_period_end_date"].notnull()
    ]

    cols = df_concated.columns
    # Assign month for all report types to avoid duplication
    df_concated["month"] = df_concated["billing_period_end_date"].copy()
    if report_type == "summary":
        pass
    elif report_type == "services":
        if "meter_category" not in cols:
            raise KeyError("meter_category column missing")
        mcat = df_concated["meter_category"].astype(str)
        df_concated = df_concated[~mcat.str.contains("Unassigned", na=False)]
    elif report_type == "marketplaces":
        if "publisher_type" not in cols:
            raise KeyError("publisher_type column missing")
        pub = df_concated["publisher_type"].astype(str)
        df_concated = df_concated[pub.str.lower() == "marketplace"]
    elif report_type == "virtualmachines":
        for col in ("meter_category", "resource_id", "additional_info"):
            if col not in cols:
                raise KeyError(f"{col} column missing")
        mcat = df_concated["meter_category"].astype(str)
        df_concated = df_concated[~mcat.str.contains("Microsoft Defender for Cloud", case=False, na=False)]
        rid = df_concated["resource_id"].astype(str)
        df_concated = df_concated[
            rid.str.contains(
                r"microsoft\.compute/virtualmachines|microsoft\.compute/disks",
                case=False,
                na=False,
                regex=True,
            )
        ]
        df_concated["additional_info"] = df_concated["additional_info"].apply(
            lambda x: (
                x
                if isinstance(x, dict)
                else (
                    json.loads(x[1:-1].replace('""', '"'))
                    if isinstance(x, str) and x.startswith('"') and x.endswith('"')
                    else (json.loads(x) if isinstance(x, str) else {})
                )
            )
        )
        df_concated = df_concated.assign(
            vm_sku=df_concated["additional_info"].map(
                lambda x: x.get("ServiceType", None) if isinstance(x, dict) else None
            )
        )
    else:
        raise ValueError("Invalid report type provided")

    required_cols = COLUMN_STACKS[report_type]
    missing_cols = [to_camel(col) for col in required_cols if col not in df_concated.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns for {report_type} report: {', '.join(missing_cols)}")

    final_cols = list(required_cols)
    return df_concated[final_cols]


# [x]: Refactor this function to be handle multiple subscription and only return the raw dataframe
def grab_from_azure(
    report_type: str,
    subscription: SubscriptionModel | list[SubscriptionModel],
    start_date=None,
    end_date=None,
):
    """Retrieves and aggregates CSV report data from Azure storage.

    This function queries the Azure storage for report files matching the specified criteria,
    downloads the CSV files, and combines them into a single pandas DataFrame.

    Parameters
    ----------
    report_type : str
        The type of report to retrieve. Must be one of the types defined in COLUMN_STACKS.
    subscription : SubscriptionModel | list[SubscriptionModel]
        The subscription(s) to filter the reports by. Not used when report_type is "summary".
    start_date : datetime, optional
        The start date for filtering reports. If None, a default start date will be used.
    end_date : datetime, optional
        The end date for filtering reports. If None, a default end date will be used.

    Returns:
        pd.DataFrame :
            A DataFrame containing the combined data from all matching CSV files.
            Returns an empty DataFrame if no data is found.

    Raises:
    ------
    ValueError
        If the provided report_type is not in COLUMN_STACKS.
    Exception
        Any exception that occurs during file reading is propagated.
    """
    import uuid
    from io import StringIO

    from caseutil import to_snake
    from django.core.files.storage import storages
    from psycopg2.extras import DateTimeTZRange

    from nilakandi.models import ExportHistory as ExportHistoryModel

    if report_type not in COLUMN_STACKS:
        raise ValueError("Invalid report type provided")

    data_source = storages["azures-storages"]
    start_date, end_date = _min_max_dates(start_date, end_date)

    q_args: dict[str, Union[DateTimeTZRange | list[uuid.UUID]]] = {
        "report_datetime_range__contained_by": DateTimeTZRange(start_date, end_date)
    }
    if report_type != "summary" or "summary" not in report_type:
        q_args["subscription__in"] = (
            [subscription.pk] if isinstance(subscription, SubscriptionModel) else [sub.pk for sub in subscription]
        )
    files_path = ExportHistoryModel.objects.filter(**q_args).values_list("blobs_path", flat=True)

    list_of_raw_data = [
        (file, data_source.size(file))
        for path in files_path
        for file in data_source.listdir(path)[1]
        if file.endswith(".csv")
    ]

    res: list[pd.DataFrame] = []
    for file, _ in list_of_raw_data:
        with data_source.open(file, "rb") as raw:
            try:
                df = pd.read_csv(
                    StringIO(raw.read().decode("utf-8")),
                    **pandas_read_csv_args,
                )
            except Exception:
                raise
            if not df.empty:
                df.columns = [to_snake(col) for col in df.columns]
                res.append(df)

    return pd.concat(res) if len(res) > 0 else pd.DataFrame()


def db_source_switch(
    report_type: str,
    subscriptions: SubscriptionModel | list[SubscriptionModel],
    start_date: date = None,
    end_date: date = None,
):
    """Retrieves and processes report data from the database for the specified report type and subscriptions.

    Parameters
    ----------
    report_type : str
        The type of report to generate. Must be one of the types defined in COLUMN_STACKS.
    subscriptions : SubscriptionModel | list[SubscriptionModel]
        A single SubscriptionModel instance or a list of SubscriptionModel instances to filter the reports by.
    start_date : date, optional
        The start date for filtering reports. If None, the earliest available date is used.
    end_date : date, optional
        The end date for filtering reports. If None, the latest available date is used.

    Returns:
        pd.DataFrame
            A DataFrame containing the processed data for the specified report type and subscriptions.

    Raises:
    ------
    ValueError
        If an invalid report type is provided.
    """
    start_date, end_date = _min_max_dates(start_date, end_date)

    # Prepare list of subscription display names and PKs
    if isinstance(subscriptions, SubscriptionModel):
        subscription_display_names = [subscriptions.display_name]
        subscription_pks = [subscriptions.pk]
    else:
        subscription_display_names = [sub.display_name for sub in subscriptions]
        subscription_pks = [sub.pk for sub in subscriptions]

    match report_type:
        case "summary":
            raw = (
                ExportReportModel.objects.filter(
                    billing_period_start_date__isnull=False,
                    billing_period_start_date__gte=start_date,
                    billing_period_end_date__isnull=False,
                    billing_period_end_date__lte=end_date,
                )
                .annotate(month=TruncMonth("billing_period_end_date"))
                .values("subscription_name", "month", "publisher_type")
                .annotate(total_cost=Sum("cost_in_billing_currency"))
                .order_by("month")
            )
        case "services":
            raw = (
                ExportReportModel.objects.filter(
                    subscription_name__in=subscription_display_names,
                    billing_period_start_date__isnull=False,
                    billing_period_start_date__gte=start_date,
                    billing_period_end_date__isnull=False,
                    billing_period_end_date__lte=end_date,
                )
                .exclude(meter_category="Unassigned")
                .annotate(month=TruncMonth("billing_period_start_date"))
                .values(
                    "meter_category",
                    "meter_sub_category",
                    "meter_name",
                    "month",
                )
                .annotate(total_cost=Sum("cost_in_billing_currency"))
                .order_by("month")
            )
        case "marketplaces":
            raw = (
                ExportReportModel.objects.filter(
                    subscription_name__in=subscription_display_names,
                    billing_period_start_date__isnull=False,
                    billing_period_start_date__gte=start_date,
                    billing_period_end_date__isnull=False,
                    billing_period_end_date__lte=end_date,
                    publisher_type__iexact="Marketplace",
                )
                .annotate(month=TruncMonth("billing_period_start_date"))
                .values("publisher_name", "plan_name", "month")
                .annotate(total_cost=Sum("cost_in_billing_currency"))
                .order_by("month")
            )
        case "virtualmachines":
            from django.db.models import Q
            from django.db.models.fields.json import KeyTextTransform

            raw = (
                ExportReportModel.objects.filter(
                    Q(resource_id__icontains="microsoft.compute/virtualmachines/")
                    | Q(resource_id__icontains="microsoft.compute/disks/")
                )
                .filter(
                    resource_id__regex="|".join(str(pk) for pk in subscription_pks),
                    billing_period_start_date__isnull=False,
                    billing_period_start_date__gte=start_date,
                    billing_period_end_date__isnull=False,
                    billing_period_end_date__lte=end_date,
                )
                .exclude(Q(meter_category__iexact="Microsoft Defender for Cloud"))
                .annotate(
                    vm_sku=KeyTextTransform("ServiceType", "additional_info"),
                )
                .values(
                    "resource_name",
                    "resource_group",
                    "tags",
                    "meter_category",
                    "resource_id",
                    "billing_period_end_date",
                    "vm_sku",
                    "cost_in_billing_currency",
                )
                .order_by("billing_period_end_date")
            )
        case _:
            raise ValueError("Invalid report type provided")
    # Return an empty DataFrame if no data is found
    if not raw or len(raw) < 1:
        return pd.DataFrame()
    return pd.DataFrame(raw)


def summary(source: pd.DataFrame) -> pd.DataFrame:
    """Generate a summary pivot table of costs by subscription name, month, and publisher type.

    This function creates a pivot table from the source DataFrame, with subscription names as rows
    and a multi-level column index of month and publisher type. The values represent the sum of
    total costs. The pivot table includes grand totals and has months sorted chronologically
    with the grand total at the end.

    Parameters
    ----------
    source : pd.DataFrame
        Source DataFrame containing at minimum the columns:
        - subscription_name: Name of the subscription
        - month: Month of the cost (date, string, or period)
        - publisher_type: Type of the publisher
        - total_cost: Cost value to be summarized

    Returns:
        pd.DataFrame
            A pivot table with:
            - Index: subscription_name
            - Columns: MultiIndex of (month, publisher_type) where month is formatted as "Month Year"
            - Values: Sum of total_cost
            - Includes grand totals

    Notes:
    -----
    If the input DataFrame is empty, returns the empty DataFrame without processing.
    Converts the "month" column to period type if it's not already in that format.
    """
    df = source
    if df.empty:
        return df
    df["month"] = pd.to_datetime(df["month"]).dt.to_period("M")
    pivot = pd.pivot_table(
        df,
        values="total_cost",
        index="subscription_name",
        columns=["month", "publisher_type"],
        aggfunc="sum",
        margins=True,
        margins_name="Grand Total",
    )

    sub_totals = []
    months = [col for col in pivot.columns.get_level_values(0).unique() if col != "Grand Total"]
    for month in months:
        month_col = [col for col in pivot.columns if col[0] == month]
        if month_col:
            month_total = pivot[month_col].sum(axis=1)
            sub_totals.append((month, "Sub Total", month_total))

    for month, sub_total_name, sub_total in sub_totals:
        pivot[(month, sub_total_name)] = sub_total

    if "Grand Total" in pivot.columns.get_level_values(0):
        grand_total_cols = pivot.xs("Grand Total", axis=1, level=0, drop_level=False)
        month_cols = pivot.drop("Grand Total", axis=1, level=0)
        month_cols = month_cols.sort_index(axis=1, level=0)
        pivot = pd.concat([month_cols, grand_total_cols], axis=1)
    else:
        pivot = pivot.sort_index(axis=1, level=0)

    pivot.columns = pd.MultiIndex.from_tuples(
        [
            (
                month.strftime("%B %Y") if isinstance(month, pd.Period) else month,
                pub_type,
            )
            for month, pub_type in pivot.columns
        ]
    )
    return pivot


def services(source: pd.DataFrame) -> pd.DataFrame:
    """Generate a pivoted cost report summarized by services (meters).

    This function processes cost data and creates a pivot table showing total costs across
    different time periods for each meter configuration. It organizes data by meter categories,
    subcategories, and individual meters with monthly columns.

    Parameters
    ----------
    source : pd.DataFrame
        Source DataFrame containing at minimum the columns 'meter_category',
        'meter_sub_category', 'meter_name', 'month', and 'total_cost'.

    Returns:
        pd.DataFrame
            A pivot table with:
            - Multi-level index of ['meter_category', 'meter_sub_category', 'meter_name']
            - Columns representing months formatted as 'MMM YYYY' (e.g., 'Jan 2022')
            - The rightmost column showing the grand total
            - Cell values representing the sum of 'total_cost'
            - Returns empty DataFrame if source is empty

    Notes:
    -----
    - Missing values in 'meter_sub_category' are filled with 'meter_category' values
    - Months are sorted chronologically with the 'Grand Total' column at the end
    """
    df = source
    if df.empty:
        return df
    df["meter_sub_category"] = df["meter_sub_category"].fillna(df["meter_category"])
    df["month"] = pd.to_datetime(df["month"]).dt.to_period("M")
    pivot = pd.pivot_table(
        df,
        values="total_cost",
        index=[
            "meter_category",
            "meter_sub_category",
            "meter_name",
        ],
        columns="month",
        aggfunc="sum",
        margins=True,
        margins_name="Grand Total",
    )
    if "Grand Total" in pivot.columns:
        grand_total_col = pivot["Grand Total"]
        month_cols = pivot.drop(columns="Grand Total")
        month_cols = month_cols.sort_index(axis=1)
        pivot = pd.concat([month_cols, grand_total_col], axis=1)
    else:
        pivot = pivot.sort_index(axis=1)
    pivot.columns = [col.strftime("%b %Y") if isinstance(col, pd.Period) else col for col in pivot.columns]
    return pivot


def marketplaces(source: pd.DataFrame) -> pd.DataFrame:
    """Generate a pivot table of marketplace costs by publisher, plan, and month.

    This function creates a pivot table from the source DataFrame, showing total costs
    for each publisher and plan across different months, with a grand total column.

    Parameters
    ----------
    source : pd.DataFrame
        Input DataFrame containing marketplace data. Expected to have columns:
        'month', 'publisher_name', 'plan_name', and 'total_cost'.

    Returns:
        pd.DataFrame
            A pivot table with:
            - Multi-index rows of 'publisher_name' and 'plan_name'
            - Columns representing months (formatted as 'MMM YYYY')
            - Values showing the sum of 'total_cost'
            - A 'Grand Total' column at the end
            - Returns empty DataFrame if source is empty

    Notes:
    -----
    The month columns are sorted chronologically, with the 'Grand Total'
    column appearing at the end of the table.
    """
    df = source
    if df.empty:
        return df
    df["month"] = pd.to_datetime(df["month"]).dt.to_period("M")
    pivot = pd.pivot_table(
        df,
        values="total_cost",
        index=["publisher_name", "plan_name"],
        columns="month",
        aggfunc="sum",
        margins=True,
        margins_name="Grand Total",
    )
    if "Grand Total" in pivot.columns:
        grand_total_col = pivot["Grand Total"]
        month_cols = pivot.drop(columns="Grand Total")
        month_cols = month_cols.sort_index(axis=1)
        pivot = pd.concat([month_cols, grand_total_col], axis=1)
    else:
        pivot = pivot.sort_index(axis=1)
    pivot.columns = [col.strftime("%b %Y") if isinstance(col, pd.Period) else col for col in pivot.columns]
    return pivot


def virtual_machines(source: pd.DataFrame) -> pd.DataFrame:
    """Process and transform Azure virtual machine cost data into a pivoted summary report.

    This function processes Azure cost data, focusing on virtual machine resources to create a
    detailed cost analysis pivot table. It performs the following operations:
    - Extracts tag values for application name, workstream, project, and owner
    - Categorizes meter entries into logical groups (VM License, VM Monthly, Storage, etc.)
    - Aggregates resources with specific prefixes (vba-, veeam-proxy-appliance)
    - Normalizes resource groups and VM names
    - Extracts VM metadata from resource IDs and tags
    - Creates a pivot table with costs grouped by VM and metadata, organized by month and meter category
    - Calculates monthly subtotals and grand totals

    Parameters
    ----------
    source : pd.DataFrame
        Source DataFrame containing Azure cost data with columns like resource_id,
        resource_name, meter_category, tags, total_cost (or cost_in_billing_currency),
        and billing_period_end_date.

    Returns:
        pd.DataFrame
            A pivot table with VM details as index (name, resource group, description, etc.),
            costs grouped by month and meter category as columns, and appropriate subtotals.

    Raises:
    ------
    ValueError
        If resource_id is empty or doesn't match expected patterns during categorization.
    """
    from re import sub

    # helper to extract tag value
    def extract_tag_value(tags, key: str) -> str:
        if isinstance(tags, str):
            try:
                return sub(r'"+', '"', tags).split(f'"{key}": "')[1].split('"')[0]
            except IndexError:
                return None
        return None

    def categorize_meter_category(row):
        r, m = getattr(row, "resource_id", ""), getattr(row, "meter_category", "")
        if not r or not isinstance(r, str):
            raise ValueError("Resource ID is None or empty", row)
        rl, ml = r.lower(), m.lower()
        if "microsoft.compute/virtualmachines" in rl:
            for k, v in (
                [["licenses"], "VM License"],
                [["machines"], "VM Monthly"],
                [["unassigned"], "Marketplace"],
                [["storage"], "Storage Cost"],
                [["network", "bandwidth"], "VM Connection"],
            ):
                if any(x in ml for x in k):
                    row.meter_category = v
                    return row
        if "microsoft.compute/disks" in rl:
            row.meter_category = "Storage Cost"
            return row
        raise ValueError("Resource ID does not match expected patterns", row)

    # helper to group and aggregate resources with a given prefix
    def aggregate_prefix(prefix: str) -> pd.DataFrame:
        subset = df[df.resource_name.str.startswith(prefix)]
        agg_df = subset.groupby("month", as_index=False).agg(agg_dict)
        return agg_df[df.columns.tolist()]

    df = source
    if df.empty:
        return df

    if "cost_in_billing_currency" in df.columns:
        df.rename({"cost_in_billing_currency": "total_cost"}, axis=1, inplace=True)
    df["total_cost"] = df["total_cost"].astype(float)
    df["month"] = pd.to_datetime(df["billing_period_end_date"]).dt.to_period("M")
    agg_dict = {col: "last" for col in df.columns if col not in ["month", "total_cost"]}
    agg_dict["total_cost"] = "sum"

    for prefix in ["vba-", "veeam-proxy-appliance"]:
        agg_df = aggregate_prefix(prefix)
        df = pd.concat([df[~df.resource_name.str.startswith(prefix)], agg_df], ignore_index=True)

    df.reset_index(drop=True, inplace=True)
    df["tags"] = df.groupby(["resource_name", "resource_group", "month"])["tags"].transform("last")

    extract_list: list[tuple[str, str]] = [
        ("description", "Application Name"),
        ("marvel_workstream", "MARVEL_WORKSTREAM"),
        ("marvel_project", "MARVEL_PROJECT"),
        ("pic_owner", "PIC owner"),
    ]
    for col, tag in extract_list:
        df[col] = df["tags"].apply(lambda x: extract_tag_value(x, tag))

    df.loc[
        df.resource_id.str.contains("microsoft.compute/virtualmachines/", case=False),
        "vm_name",
    ] = df["resource_name"]
    df.loc[df.resource_id.str.contains("microsoft.compute/disks/", case=False), "vm_name"] = df["tags"].apply(
        lambda x: extract_tag_value(x, "VM Name")
    )

    df.loc[df.resource_name.str.startswith(("vba-", "VBA-")), "vm_name"] = "VBA Workers VM"
    df.loc[df.resource_name.str.startswith("veeam-proxy-appliance"), "vm_name"] = "veeam-proxy-appliance"

    df[["meter_category", "resource_id"]] = df[["meter_category", "resource_id"]].apply(
        categorize_meter_category, axis=1
    )

    df.resource_group = df.resource_group.str.upper()
    df.vm_name = df.vm_name.str.upper()
    only_details = (
        df[
            [
                "vm_name",
                "billing_period_end_date",
                "resource_group",
                "description",
                "marvel_workstream",
                "marvel_project",
                "pic_owner",
                "vm_sku",
            ]
        ]
        .sort_values(by=["billing_period_end_date"])
        .groupby("vm_name")
        .last()
        .reset_index()
        .fillna("-")
    )

    df.vm_sku = df.groupby(["vm_name"])["vm_sku"].transform(
        lambda x: x.dropna().mode().iloc[0] if not x.dropna().mode().empty else None
    )
    df.pic_owner = df.groupby(["vm_name"])["pic_owner"].transform(
        lambda x: x.dropna().mode().iloc[0] if not x.dropna().mode().empty else None
    )
    # Merge only necessary columns from only_details into df to save memory
    df = df.merge(
        only_details,
        how="left",
        left_on="vm_name",
        right_on="vm_name",
        suffixes=("", "_details"),
    )
    df.fillna(
        {
            "vm_name": "-",
            "resource_group_details": "-",
            "description_details": "-",
            "marvel_workstream_details": "-",
            "marvel_project_details": "-",
            "pic_owner_details": "-",
            "vm_sku_details": "-",
        },
        inplace=True,
    )

    pivot = pd.pivot_table(
        df,
        values="total_cost",
        index=[
            "vm_name",
            "resource_group_details",
            "description_details",
            "marvel_workstream_details",
            "marvel_project_details",
            "pic_owner_details",
            "vm_sku_details",
        ],
        columns=["month", "meter_category"],
        aggfunc="sum",
        margins=True,
        margins_name="Grand Total",
    )

    # Sub Totals Calculation
    sub_totals = []
    months = [col for col in pivot.columns.get_level_values(0).unique() if col != "Grand Total"]
    for month in months:
        month_col = [col for col in pivot.columns if col[0] == month]
        if month_col:
            month_total = pivot[month_col].sum(axis=1)
            sub_totals.append((month, "Sub Total", month_total))

    for month, sub_total_name, sub_total in sub_totals:
        pivot[(month, sub_total_name)] = sub_total

    sorted_cols = []
    for month in months:
        month_cols = [col for col in pivot.columns if col[0] == month and col[1] != "Sub Total"]
        sorted_cols.extend(month_cols)
        sub_total_col = (month, "Sub Total")
        if sub_total_col in pivot.columns:
            sorted_cols.append(sub_total_col)

    grand_total_cols = [col for col in pivot.columns if col[0] == "Grand Total"]
    sorted_cols.extend(grand_total_cols)

    pivot = pivot[sorted_cols]

    pivot.columns = pd.MultiIndex.from_tuples(
        [
            (
                month.strftime("%B %Y") if isinstance(month, pd.Period) else month,
                pub_type,
            )
            for month, pub_type in pivot.columns
        ]
    )
    return pivot
