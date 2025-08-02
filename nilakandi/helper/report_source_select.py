"""Report Source Selection Module.

This module provides functionality for gathering and pivoting data for report generation
from various sources. It serves as a bridge between different data sources (database, Azure,
or user-provided files) and the report generation components of the nilakandi system.

The module contains two main functions:
- gather_data: Collects data from specified sources for report generation
- pivoting_data: Transforms collected data into the appropriate format for different report types

These functions support various report types including summary, services, marketplaces,
and virtual machine reports. The module works with subscription data and handles
date ranges for filtering report data.

This module is designed to be used as part of the nilakandi reporting pipeline and
interfaces with other report generation helpers.
"""

from datetime import datetime

from pandas import DataFrame

from nilakandi.helper.report_generation import marketplaces as marketplacesReport
from nilakandi.helper.report_generation import services as servicesReport
from nilakandi.helper.report_generation import summary as summaryReport
from nilakandi.helper.report_generation import virtual_machines as virtualmachinesReport
from nilakandi.models import Subscription as SubscriptionsModel


# [x]: Refactor this function to be more modular and handle different data sources more gracefully.
def gather_data(
    report_type: str,
    start_date: datetime.date,
    end_date: datetime.date,
    subscriptions: SubscriptionsModel | list[SubscriptionsModel],
    source: str = "db",
    file_list: list[str] = [],
) -> DataFrame:
    """Gather data for report generation from various sources.

    This function collects data for reports from different sources (database, Azure, or bring your own file)
    based on the specified parameters.

    Args:
        report_type (str): The type of report to generate.
        start_date (datetime.date): The start date for the report data range.
        end_date (datetime.date): The end date for the report data range.
        subscriptions (SubscriptionsModel | list[SubscriptionsModel]): The subscription(s) to gather data for.
        source (str, optional): The data source to use.
                                Options are "db" (default), "azure", or "byof" (bring your own file).
        file_list (list[str], optional): List of file paths when using "byof" source. Defaults to empty list.

    Returns:
        DataFrame: A DataFrame containing the gathered data for the specified report type and subscriptions.

    Raises:
        ValueError: If source is "byof" and file_list is empty.
    """
    from nilakandi.helper.report_generation import byof_source_switch, db_source_switch, grab_from_azure

    match source:
        case "azure":
            data = grab_from_azure(
                report_type=report_type,
                subscription=subscriptions,
                start_date=start_date,
                end_date=end_date,
            )
        case "byof":
            if file_list.__len__() == 0:
                raise ValueError("File list cannot be empty for BYOF source.")
            data = byof_source_switch(
                file_paths=file_list,
            )
            # if task_id is not None and not data.empty and date_range is not (NaT, NaT):
            #     from psycopg2.extras import DateTimeTZRange

            #     min_date, max_date = date_range
            #     generated_report = GeneratedReportsModel.objects.get(id=task_id)
            #     generated_report.time_range = DateTimeTZRange(min_date, max_date)
            #     generated_report.save(update_fields=["time_range"])
        case _:
            data = db_source_switch(
                report_type=report_type,
                subscriptions=subscriptions,
                start_date=start_date,
                end_date=end_date,
            )
    return data


# [x]: Refactor this piece as a new function detach from the above function.
def pivoting_data(
    report_type: str,
    data: DataFrame,
    subscription_name: str,
) -> tuple[str, DataFrame]:
    """Pivots data for different report types based on the specified parameters.

    This function delegates report generation to specialized report functions based on the
    report type. It processes the given DataFrame and returns a formatted report title
    along with the processed data.

    Args:
        report_type (str): Type of report to generate. Must be one of: "summary",
                           "services", "marketplaces", or "virtualmachines".
        data (DataFrame): The source data to process for the report.
        decimal_count (int): Number of decimal places to round numeric values to.
        subscription_name (str): Subscription name to include in the report title.

    Returns:
        tuple[str, DataFrame]: A tuple containing the report title and the processed DataFrame.
    """
    report_func: dict[str, callable] = {
        "summary": summaryReport,
        "services": servicesReport,
        "marketplaces": marketplacesReport,
        "virtualmachines": virtualmachinesReport,
    }
    title = f"{subscription_name} - {report_type.capitalize()} Report" if report_type != "summary" else "Summary Report"
    res: tuple[str, DataFrame] = (title, report_func[report_type](data))
    return res
