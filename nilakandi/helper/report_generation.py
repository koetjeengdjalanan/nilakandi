from datetime import date

import pandas as pd
from django.db.models import Max, Min, Sum
from django.db.models.functions import TruncMonth

from nilakandi.models import ExportReport as ExportReportModel
from nilakandi.models import Subscription as SubscriptionModel


def summary(start_date: date = None, end_date: date = None) -> pd.DataFrame:
    if start_date is None or end_date is None:
        dates = ExportReportModel.objects.aggregate(
            min_date=Min("billing_period_start_date"),
            max_date=Max("billing_period_end_date"),
        )
        start_date = start_date or dates["min_date"]
        end_date = end_date or dates["max_date"]

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
    df = pd.DataFrame(raw)
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


def services(
    subscription: SubscriptionModel, start_date: date = None, end_date: date = None
) -> pd.DataFrame:
    if start_date is None or end_date is None:
        dates = ExportReportModel.objects.aggregate(
            min_date=Min("billing_period_start_date"),
            max_date=Max("billing_period_end_date"),
        )
        start_date = start_date or dates["min_date"]
        end_date = end_date or dates["max_date"]
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
    df = pd.DataFrame(raw)
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


def marketplaces(
    subscription: SubscriptionModel, start_date: date = None, end_date: date = None
) -> pd.DataFrame:
    if start_date is None or end_date is None:
        dates = ExportReportModel.objects.aggregate(
            min_date=Min("billing_period_start_date"),
            max_date=Max("billing_period_end_date"),
        )
        start_date = start_date or dates["min_date"]
        end_date = end_date or dates["max_date"]

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
    df = pd.DataFrame(raw)
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


def virtual_machine(
    subscription: SubscriptionModel, start_date: date = None, end_date: date = None
) -> pd.DataFrame:
    from django.db.models import Max, Min, Q
    from django.db.models.fields.json import KeyTextTransform

    # helper to extract tag value
    def extract_tag_value(tags, key: str) -> str:
        if isinstance(tags, str):
            try:
                return tags.split(f'"{key}": "')[1].split('"')[0]
            except IndexError:
                return None
        return None

    def categorize_meter_category(row: pd.Series) -> pd.Series:
        COMPARISON = [
            (["licenses"], "VM License"),
            (["machines"], "VM Monthly"),
            (["unassigned"], "Marketplace"),
            (["storage"], "Storage Cost"),
            (["network", "bandwidth"], "VM Connection"),
        ]

        if "microsoft.compute/virtualmachines" in row.resource_id.lower():
            for keywords, new_value in COMPARISON:
                if any(kw in row.meter_category.lower() for kw in keywords):
                    row.meter_category = new_value
                    return row
        if "microsoft.compute/disks" in row.resource_id.lower():
            row.meter_category = "Storage Cost"
            return row
        raise ValueError("Resource ID is None or empty", row)
        return row

    if start_date is None or end_date is None:
        dates = ExportReportModel.objects.aggregate(
            min_date=Min("billing_period_start_date"),
            max_date=Max("billing_period_end_date"),
        )
        start_date = start_date or dates["min_date"]
        end_date = end_date or dates["max_date"]

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
    df = pd.DataFrame(raw)
    if df.empty:
        return df

    df.rename({"cost_in_billing_currency": "total_cost"}, axis=1, inplace=True)
    df["total_cost"] = df["total_cost"].astype(float)
    df["month"] = pd.to_datetime(df["billing_period_end_date"]).dt.to_period("M")
    agg_dict = {col: "last" for col in df.columns if col not in ["month", "total_cost"]}
    agg_dict["total_cost"] = "sum"

    # helper to group and aggregate resources with a given prefix
    def aggregate_prefix(prefix: str) -> pd.DataFrame:
        subset = df[df.resource_name.str.startswith(prefix)]
        agg_df = subset.groupby("month", as_index=False).agg(agg_dict)
        return agg_df[df.columns.tolist()]

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
