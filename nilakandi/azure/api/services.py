from datetime import datetime as dt
from datetime import timedelta
from re import sub
from sys import stderr
from zoneinfo import ZoneInfo as zi

import pandas as pd
from requests import post

from config.django.base import TIME_ZONE
from nilakandi.azure.models import ApiResult
from nilakandi.models import Services as ServicesModel
from nilakandi.models import Subscription as SubscriptionsModel


class Services:
    def __init__(
        self,
        bearer_token: str,
        subscription: SubscriptionsModel,
        base_url: str = "https://management.azure.com",
        end_date: dt = dt.now(tz=zi(TIME_ZONE)),
        start_date: dt | None = None,
    ):
        if end_date - start_date > timedelta(days=365):
            raise ValueError("Date range must be within 1 year")
        if end_date < start_date:
            raise ValueError("End date must be greater than start date")
        self.bearer_token: str = bearer_token
        self.subscription: SubscriptionsModel = subscription
        self.end_date: dt = end_date
        self.res = None
        self.start_date: dt = (
            start_date if start_date else end_date - timedelta(days=30)
        )
        self.uri: str = (
            f"{base_url}{self.subscription.id}/providers/Microsoft.CostManagement/query"
        )
        self.params: dict[str, str] = {
            "api-version": "2019-11-01",
        }
        self.headers: dict[str, str] = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "ClientType": "Nilakandi-NTT",
            "x-ms-command-name": "CostAnalysis",
        }
        self.payload: dict[str, str | dict] = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {
                "from": self.start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "to": self.end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            },
            "dataset": {
                "granularity": "Daily",
                "aggregation": {"totalCost": {"name": "CostUSD", "function": "Sum"}},
                "grouping": [
                    {"type": "Dimension", "name": "SubscriptionId"},
                    {"type": "Dimension", "name": "ChargeType"},
                    {"type": "Dimension", "name": "ServiceName"},
                    {"type": "Dimension", "name": "ServiceTier"},
                    {"type": "Dimension", "name": "Meter"},
                    {"type": "Dimension", "name": "PartNumber"},
                    {"type": "Dimension", "name": "BillingMonth"},
                    {"type": "Dimension", "name": "ResourceId"},
                    {"type": "Dimension", "name": "ResourceType"},
                ],
            },
        }

    def pull(self, uri: str | None = None) -> "Services":
        try:
            reqRes = post(
                url=self.uri if (uri is None) else uri,
                params=self.params if (uri is None) else None,
                headers=self.headers,
                json=self.payload,
            )
            reqRes.raise_for_status()
        except Exception as e:
            print(
                e.response.headers,
                e.response.json(),
                sep="\n",
                end=f"\n{"="*100}\n",
                file=stderr,
            )
            self.res: ApiResult = ApiResult(
                status=reqRes.status_code,
                headers=reqRes.headers,
                data=pd.DataFrame(),
                next_link=self.res.next_link,
                raw=reqRes.json(),
                meta=None,
            )
            raise Exception("Services Post Request Failed") from e
        res = reqRes.json().copy()
        columns = [
            sub(
                r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
                "_",
                col["name"],
            ).lower()
            for col in res["properties"]["columns"]
        ]
        rows = [dict(zip(columns, row)) for row in res["properties"]["rows"]]

        self.res: ApiResult = ApiResult(
            status=reqRes.status_code,
            headers=reqRes.headers,
            data=pd.DataFrame(data=rows),
            next_link=res.get("properties").get("nextLink"),
            raw=rows,
            meta={
                key: value
                for key, value in res.items()
                if key not in ["columns", "rows", "properties"]
            },
        )
        return self

    def db_save(self) -> "Services":
        if not isinstance(self.res, ApiResult):
            raise ValueError("No data to save")
        data: list[ServicesModel] = [
            ServicesModel(
                subscription=self.subscription,
                usage_date=dt.strptime(str(row["usage_date"]), "%Y%m%d"),
                charge_type=row["charge_type"],
                service_name=row["service_name"],
                service_tier=row["service_tier"],
                meter=row["meter"],
                part_number=row["part_number"],
                billing_month=dt.fromisoformat(row["billing_month"]).date(),
                resource_id=row["resource_id"],
                resource_type=row["resource_type"],
                cost_usd=row["cost_usd"],
                currency=row["currency"],
            )
            for index, row in self.res.data.iterrows()
        ]
        ServicesModel.objects.bulk_create(data, batch_size=500)
        return self
