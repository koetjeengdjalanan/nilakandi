from datetime import datetime
from uuid import UUID

from pandas import DataFrame, NaT

from nilakandi.helper.miscellaneous import df_tohtml
from nilakandi.helper.report_generation import marketplaces as marketplacesReport
from nilakandi.helper.report_generation import services as servicesReport
from nilakandi.helper.report_generation import summary as summaryReport
from nilakandi.helper.report_generation import virtual_machine as virtualmachinesReport
from nilakandi.models import GeneratedReports as GeneratedReportsModel
from nilakandi.models import Subscription as SubscriptionsModel


def gather_data(
    report_type: str,
    decimal_count: int,
    start_date: datetime.date,
    end_date: datetime.date,
    subscription: SubscriptionsModel,
    source: str = "db",
    file_list: list[str] = [],
    task_id: UUID | None = None,
) -> tuple[str, str, DataFrame]:
    from nilakandi.helper.report_generation import (
        byof_source_switch,
        db_source_switch,
        grab_from_azure,
    )

    match source:
        case "azure":
            data = grab_from_azure(
                report_type=report_type,
                subscription=subscription,
                start_date=start_date,
                end_date=end_date,
            )
        case "byof":
            if file_list.__len__() == 0:
                raise ValueError("File list cannot be empty for BYOF source.")
            date_range, data = byof_source_switch(
                report_type=report_type,
                file_paths=file_list,
                subscription_name=subscription.display_name,
            )
            if task_id is not None and not data.empty and date_range is not (NaT, NaT):
                from psycopg2.extras import DateTimeTZRange

                min_date, max_date = date_range
                generated_report = GeneratedReportsModel.objects.get(id=task_id)
                generated_report.time_range = DateTimeTZRange(min_date, max_date)
                generated_report.save(update_fields=["time_range"])
        case _:
            data = db_source_switch(
                report_type=report_type,
                subscription=subscription,
                start_date=start_date,
                end_date=end_date,
            )

    match report_type:
        case "summary":
            page_title = "Summary Report"
            pivot = df_tohtml(
                df=summaryReport(data),
                decimal=decimal_count,
            )
        case "services":
            page_title = f"{subscription.display_name} - Services Report"
            pivot = df_tohtml(
                df=servicesReport(data),
                decimal=decimal_count,
            )
        case "marketplaces":
            page_title = f"{subscription.display_name} - Marketplaces Report"
            pivot = df_tohtml(
                marketplacesReport(data),
                decimal=decimal_count,
            )
        case "virtualmachines":
            page_title = f"{subscription.display_name} - Virtual Machines Report"
            pivot = df_tohtml(
                virtualmachinesReport(data),
                decimal=decimal_count,
            )
    return (page_title, pivot, data)
