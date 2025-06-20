import logging
from datetime import date
from typing import Dict

import pandas as pd
from django.db.models import Max, Min, Sum
from django.db.models.functions import TruncMonth

from nilakandi.models import ExportReport as ExportReportModel
from nilakandi.models import Subscription as SubscriptionModel

COLUMN_STACKS: Dict[str, tuple[str]] = {
    "summary": ["subscription_name", "month", "publisher_type", "total_cost"],
    "services": [
        "meter_category",
        "meter_sub_category",
        "meter_name",
        "month",
        "total_cost",
    ],
    "marketplaces": ["publisher_name", "plan_name", "month", "total_cost"],
    "virtualmachines": [
        "resource_name",
        "resource_group",
        "tags",
        "meter_category",
        "resource_id",
        "billing_period_end_date",
        "total_cost",
        "vm_sku",
    ],
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


def byof_source_switch(report_type: str, file_paths: list[str]):
    import os
    from io import StringIO

    from caseutil import to_snake

    res = []
    files = file_paths[0] if isinstance(file_paths[0], list) else file_paths
    for file in files:
        if not file.endswith(".csv"):
            raise ValueError(
                f"Invalid file format: {file}. Only CSV files are allowed."
            )
        with open(file, "rb") as raw:
            try:
                df = pd.read_csv(
                    StringIO(raw.read().decode("utf-8")),
                    parse_dates=[
                        "Date",
                        "BillingPeriodStartDate",
                        "BillingPeriodEndDate",
                    ],
                    date_format="%m/%d/%Y",
                    cache_dates=True,
                    engine="python",
                    encoding="utf-8",
                    sep=r',(?=(?:[^"]*"[^"]*")*[^"]*$)',
                    quotechar='"',
                    on_bad_lines="error",
                )
            except Exception:
                raise
            if not df.empty:
                df.columns = [to_snake(col) for col in df.columns]
                res.append(df)
    if res.__len__() == 0:
        return pd.DataFrame()

    processed_df = process_csv_file(res, report_type)
    for file in files:
        try:
            os.remove(file)
        except OSError as e:
            logging.getLogger("nilakandi.tasks").error(
                f"Error deleting file {file}: {e}"
            )

    return processed_df


def process_csv_file(
    input_dataframes: list[pd.DataFrame], report_type: str
) -> pd.DataFrame:
    df_concated = pd.concat(input_dataframes, ignore_index=True)
    if "cost_in_billing_currency" in df_concated.columns:
        df_concated.rename(
            columns={"cost_in_billing_currency": "total_cost"}, inplace=True
        )

    for col in ("billing_period_start_date", "billing_period_end_date"):
        if col not in df_concated.columns:
            raise KeyError(f"{col} column missing in data")
    df_concated = df_concated[
        df_concated["billing_period_start_date"].notnull()
        & df_concated["billing_period_end_date"].notnull()
    ]

    cols = df_concated.columns
    if report_type == "summary":
        pass
    elif report_type == "services":
        if "meter_category" not in cols:
            raise KeyError("meter_category column missing")
        mcat = df_concated["meter_category"].astype(str)
        df_concated["month"] = df_concated["billing_period_end_date"].copy()
        df_concated = df_concated[~mcat.str.contains("Unassigned", na=False)]
    elif report_type == "marketplaces":
        if "publisher_type" not in cols:
            raise KeyError("publisher_type column missing")
        pub = df_concated["publisher_type"].astype(str)
        df_concated["month"] = df_concated["billing_period_end_date"].copy()
        df_concated = df_concated[pub.str.lower() == "marketplace"]
    elif report_type == "virtualmachines":
        for col in ("meter_category", "resource_id", "additional_info"):
            if col not in cols:
                raise KeyError(f"{col} column missing")
        mcat = df_concated["meter_category"].astype(str)
        df_concated = df_concated[
            ~mcat.str.contains("Microsoft Defender for Cloud", case=False, na=False)
        ]
        rid = df_concated["resource_id"].astype(str)
        df_concated = df_concated[
            rid.str.contains(
                r"microsoft\.compute/virtualmachines|microsoft\.compute/disks",
                case=False,
                na=False,
                regex=True,
            )
        ]
        df_concated = df_concated.assign(
            vm_sku=df_concated["additional_info"].map(
                lambda x: x.get("ServiceType") if isinstance(x, dict) else None
            )
        )
    else:
        raise ValueError("Invalid report type provided")

    final_cols = [
        col for col in COLUMN_STACKS[report_type] if col in df_concated.columns
    ]
    if not final_cols:
        raise KeyError(f"No columns found for report type {report_type}")
    return df_concated[final_cols]


def grab_from_azure(
    report_type: str,
    subscription,
    start_date=None,
    end_date=None,
):
    from io import StringIO

    from caseutil import to_snake
    from django.core.files.storage import storages
    from psycopg2.extras import DateTimeTZRange

    from nilakandi.models import ExportHistory as ExportHistoryModel

    if report_type not in COLUMN_STACKS:
        raise ValueError("Invalid report type provided")

    data_source = storages["azures-storages"]
    start_date, end_date = _min_max_dates(start_date, end_date)

    q_args = {
        "report_datetime_range__contained_by": DateTimeTZRange(start_date, end_date)
    }
    if report_type != "summary":
        q_args["subscription"] = subscription.pk
    files_path = ExportHistoryModel.objects.filter(**q_args).values_list(
        "blobs_path", flat=True
    )

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
                    parse_dates=[
                        "Date",
                        "BillingPeriodStartDate",
                        "BillingPeriodEndDate",
                    ],
                    date_format="%m/%d/%Y",
                    cache_dates=True,
                    engine="python",
                    encoding="utf-8",
                    sep=r',(?=(?:[^"]*"[^"]*")*[^"]*$)',
                    quotechar='"',
                    on_bad_lines="error",
                )
            except Exception:
                raise
            if not df.empty:
                df.columns = [to_snake(col) for col in df.columns]
                res.append(df)

    if not res:
        return pd.DataFrame()

    return process_csv_file(res, report_type)
    # df_concated = pd.concat(res, ignore_index=True)
    # if "cost_in_billing_currency" in df_concated.columns:
    #     df_concated.rename(
    #         columns={"cost_in_billing_currency": "total_cost"}, inplace=True
    #     )

    # for col in ("billing_period_start_date", "billing_period_end_date"):
    #     if col not in df_concated.columns:
    #         raise KeyError(f"{col} column missing in data")
    # df_concated = df_concated[
    #     df_concated["billing_period_start_date"].notnull()
    #     & df_concated["billing_period_end_date"].notnull()
    # ]

    # cols = df_concated.columns
    # if report_type == "summary":
    #     pass
    # elif report_type == "services":
    #     if "meter_category" not in cols:
    #         raise KeyError("meter_category column missing")
    #     mcat = df_concated["meter_category"].astype(str)
    #     df_concated = df_concated[~mcat.str.contains("Unassigned", na=False)]
    # elif report_type == "marketplaces":
    #     if "publisher_type" not in cols:
    #         raise KeyError("publisher_type column missing")
    #     pub = df_concated["publisher_type"].astype(str)
    #     df_concated = df_concated[pub.str.lower() == "marketplace"]
    # elif report_type == "virtualmachines":
    #     for col in ("meter_category", "resource_id", "additional_info"):
    #         if col not in cols:
    #             raise KeyError(f"{col} column missing")
    #     mcat = df_concated["meter_category"].astype(str)
    #     df_concated = df_concated[
    #         ~mcat.str.contains("Microsoft Defender for Cloud", case=False, na=False)
    #     ]
    #     rid = df_concated["resource_id"].astype(str)
    #     df_concated = df_concated[
    #         rid.str.contains(
    #             r"microsoft\.compute/virtualmachines|microsoft\.compute/disks",
    #             case=False,
    #             na=False,
    #             regex=True,
    #         )
    #     ]
    #     df_concated = df_concated.assign(
    #         vm_sku=df_concated["additional_info"].map(
    #             lambda x: x.get("ServiceType") if isinstance(x, dict) else None
    #         )
    #     )
    # else:
    #     raise ValueError("Invalid report type provided")

    # final_cols = [
    #     col for col in COLUMN_STACKS[report_type] if col in df_concated.columns
    # ]
    # if not final_cols:
    #     raise KeyError(f"No columns found for report type {report_type}")
    # return df_concated[final_cols]


def db_source_switch(
    report_type: str,
    subscription: SubscriptionModel,
    start_date: date = None,
    end_date: date = None,
):

    start_date, end_date = _min_max_dates(start_date, end_date)

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
                    subscription_name__contains=subscription.display_name,
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
                    subscription_name__contains=subscription.display_name,
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
                    Q(resource_id__icontains="microsoft.compute/virtualmachines")
                    | Q(resource_id__icontains="microsoft.compute/disks")
                )
                .filter(
                    resource_id__icontains=subscription.pk,
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
    return pd.DataFrame(raw)


def summary(source: pd.DataFrame) -> pd.DataFrame:
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
    pivot.columns = [
        col.strftime("%b %Y") if isinstance(col, pd.Period) else col
        for col in pivot.columns
    ]
    return pivot


def marketplaces(source: pd.DataFrame) -> pd.DataFrame:
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
    pivot.columns = [
        col.strftime("%b %Y") if isinstance(col, pd.Period) else col
        for col in pivot.columns
    ]
    return pivot


def virtual_machine(source: pd.DataFrame) -> pd.DataFrame:
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
        df = pd.concat(
            [df[~df.resource_name.str.startswith(prefix)], agg_df], ignore_index=True
        )

    df.reset_index(drop=True, inplace=True)
    df["tags"] = df.groupby(["resource_name", "resource_group", "month"])[
        "tags"
    ].transform("last")

    extract_list: list[tuple[str, str]] = [
        ("description", "Application Name"),
        ("marvel_workstream", "MARVEL_WORKSTREAM"),
        ("marvel_project", "MARVEL_PROJECT"),
        ("pic_owner", "PIC owner"),
    ]
    for col, tag in extract_list:
        df[col] = df["tags"].apply(lambda x: extract_tag_value(x, tag))

    df.loc[
        df.resource_id.str.contains("microsoft.compute/virtualmachines", case=False),
        "vm_name",
    ] = df["resource_name"]
    df.loc[
        df.resource_id.str.contains("microsoft.compute/disks", case=False), "vm_name"
    ] = df["tags"].apply(lambda x: extract_tag_value(x, "VM Name"))

    df.loc[df.resource_name.str.startswith(("vba-", "VBA-")), "vm_name"] = (
        "VBA Workers VM"
    )
    df.loc[df.resource_name.str.startswith("veeam-proxy-appliance"), "vm_name"] = (
        "veeam-proxy-appliance"
    )

    df[["meter_category", "resource_id"]] = df[["meter_category", "resource_id"]].apply(
        categorize_meter_category, axis=1
    )

    df.resource_group = df.resource_group.str.upper()
    df.vm_name = df.vm_name.str.upper()

    df.vm_sku = df.groupby(["vm_name", "resource_group", "description"])[
        "vm_sku"
    ].transform(
        lambda x: x.dropna().mode().iloc[0] if not x.dropna().mode().empty else None
    )
    df.pic_owner = df.groupby(["vm_name", "resource_group", "description"])[
        "pic_owner"
    ].transform(
        lambda x: x.dropna().mode().iloc[0] if not x.dropna().mode().empty else None
    )
    df.fillna(
        {
            "vm_name": "-",
            "resource_group": "-",
            "description": "-",
            "marvel_workstream": "-",
            "marvel_project": "-",
            "pic_owner": "-",
            "vm_sku": "-",
        },
        inplace=True,
    )

    pivot = pd.pivot_table(
        df,
        values="total_cost",
        index=[
            "vm_name",
            "resource_group",
            "description",
            "marvel_workstream",
            "marvel_project",
            "pic_owner",
            "vm_sku",
        ],
        columns=["month", "meter_category"],
        aggfunc="sum",
        margins=True,
        margins_name="Grand Total",
    )
    # Place Grand Total columns at the end if they exist
    if "Grand Total" in pivot.columns.get_level_values(0):
        grand_total_cols = pivot.xs("Grand Total", axis=1, level=0, drop_level=False)
        month_cols = pivot.drop("Grand Total", axis=1, level=0).sort_index(
            axis=1, level=0
        )
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
