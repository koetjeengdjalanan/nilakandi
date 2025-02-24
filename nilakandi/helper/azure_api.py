import uuid

from pandas import DataFrame
from re import sub
from datetime import datetime as dt, timedelta
from zoneinfo import ZoneInfo
import requests

from azure.identity import ClientSecretCredential
from azure.mgmt.consumption import ConsumptionManagementClient
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.costmanagement.models import (
    QueryDefinition,
    QueryDataset,
    QueryAggregation,
    QueryGrouping,
    QueryTimePeriod,
    QueryResult,
)

from config.django.base import TIME_ZONE
from nilakandi.models import (
    Subscription as SubscriptionsModel,
    Services as ServicesModel,
    Marketplace as MarketplacesModel,
)


class Auth:
    """
    Azure API Authentication class
    """

    def __init__(self, client_id: str, tenant_id: str, client_secret: str) -> None:
        """Class Initializer

        Args:
            client_id (str): Id of API User
            tenant_id (str): Tenant Id
            client_secret (str): Password for the API User
        """
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.client_secret = client_secret
        self.credential: ClientSecretCredential = ClientSecretCredential(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        self.token = self.credential.get_token(
            "https://management.azure.com/.default")


class Services:
    """Azure API Services class to get data from Azure API
    """

    def __init__(
        self,
        auth: Auth,
        subscription: SubscriptionsModel,
        end_date: dt = dt.now(ZoneInfo(TIME_ZONE)),
        start_date: dt | None = None,
    ) -> None:
        self.auth = auth
        self.subscription: SubscriptionsModel = subscription
        self.startDate = start_date if start_date else end_date - \
            timedelta(days=7)
        self.endDate = end_date

    def get(self) -> "Services":
        """Get from Azure API

        Returns:
            Services: Azure API Services object
        """
        client = CostManagementClient(credential=self.auth.credential)
        self.scope = self.subscription.id
        self.query = QueryDefinition(
            type="ActualCost",
            timeframe="Custom",
            time_period=QueryTimePeriod(
                from_property=self.startDate,
                to=self.endDate,
            ),
            dataset=QueryDataset(
                granularity="Daily",
                aggregation={
                    "totalCost": QueryAggregation(name="CostUSD", function="Sum")
                },
                grouping=[
                    QueryGrouping(name="SubscriptionId", type="Dimension"),
                    QueryGrouping(name="ChargeType", type="Dimension"),
                    QueryGrouping(name="ServiceName", type="Dimension"),
                    QueryGrouping(name="ServiceTier", type="Dimension"),
                    QueryGrouping(name="Meter", type="Dimension"),
                    QueryGrouping(name="PartNumber", type="Dimension"),
                    QueryGrouping(name="BillingMonth", type="Dimension"),
                    QueryGrouping(name="ResourceId", type="Dimension"),
                    QueryGrouping(name="ResourceType", type="Dimension"),
                    # QueryGrouping(name="VM Name", type="TagKey"),
                ],
            ),
        )
        self.clientale = client.query
        self.queryRes: QueryResult = self.clientale.usage(
            scope=self.scope, parameters=self.query)
        self.nextLink: str = self.queryRes.next_link
        self.res: DataFrame = DataFrame(
            data=self.queryRes.rows, columns=[
                sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", col.name).lower() for col in self.res.columns
            ]
        )
        return self

    def next(self, next_uri: str | None = None) -> "Services":
        if (not self.nextLink) or (self.nextLink is None):
            raise ValueError("No next link")
        payload = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {
                "from": self.query.time_period.as_dict()['from_property'],
                "to": self.query.time_period.as_dict()['to']
            },
            "dataset": self.query.dataset.as_dict()
        }
        try:
            next_res = requests.post(
                url=self.nextLink if not next_uri else next_uri,
                headers={
                    "Authorization": f"Bearer {self.auth.token.token}",
                    "Content-Type": "application/json",
                    "User-Agent": str(self.clientale._config.user_agent_policy._user_agent)
                },
                json=payload,
            )
            next_res.raise_for_status()
        except requests.HTTPError as e:
            raise e
        self.nextLink: str = next_res['properties']['nextLink']
        self.res: DataFrame = DataFrame(
            next_res['properties']['rows'], columns=[
                sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", col['name']).lower() for col in next_res['properties']['columns']
            ]
        )
        return self

    def db_save(self, ignore_conflicts: bool = False, update_conflicts: bool = True, check_conflic_on_create: bool = True) -> "Services":
        """Save data to DB

        Args:
            ignore_conflicts (bool, optional): Should DB ignore conficted data. Defaults to False.
            update_conflicts (bool, optional): Should DB update conflicted data. Defaults to True.
            check_conflic_on_create (bool, optional): If data confilcting should it be updated. Defaults to True.

        Returns:
            Services: Azure API Services object
        """
        if not isinstance(self.res, DataFrame) or self.res.empty:
            raise ValueError("No data to save")
        data: list[ServicesModel] = [
            ServicesModel(
                subscription=self.subscription,
                usage_date=dt.strptime(
                    str(row["usage_date"]), "%Y%m%d") if "usage_date" in row else dt.now(ZoneInfo(TIME_ZONE)),
                charge_type=row["charge_type"] if "charge_type" in row else None,
                service_name=row["charge_type"] if "charge_type" in row else None,
                service_tier=row["charge_type"] if "charge_type" in row else None,
                meter=row["charge_type"] if "charge_type" in row else None,
                part_number=row["charge_type"] if "charge_type" in row else None,
                billing_month=row["charge_type"] if "charge_type" in row else None,
                resource_id=row["charge_type"] if "charge_type" in row else None,
                resource_type=row["charge_type"] if "charge_type" in row else None,
                cost_usd=row["charge_type"] if "charge_type" in row else None,
                currency=row["charge_type"] if "charge_type" in row else None,
            )
            for row in self.res.iterrows()
        ]
        if check_conflic_on_create:
            ServicesModel.objects.bulk_create(
                data,
                batch_size=500,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
                unique_fields=["usage_date", "service_name",
                               "service_tier", "meter"],
                update_fields=["charge_type",
                               "part_number", "cost_usd", "currency"]
            )
        else:
            ServicesModel.objects.bulk_create(
                data,
                batch_size=500,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts
            )
        return self

    def __dict__(self) -> dict:
        return self.res.as_dict() if self.res else {}


class Subscriptions:
    """Subscriptions class to get all subscriptions from Azure API
    use Azure API SubscriptionClient
    """

    def __init__(self, auth: Auth) -> None:
        """Class Initializer

        Args:
            auth (Auth): Auth object
        """
        self.auth = auth

    def get(self) -> "Subscriptions":
        """Get Data from Azure API

        Returns:
            Subscriptions: Azure Api Subscriptions object
        """
        client = SubscriptionClient(credential=self.auth.credential)
        self.res = [item.as_dict() for item in client.subscriptions.list()]
        return self

    def db_save(self) -> "Subscriptions":
        """Save Data to DB

        Raises:
            ValueError: self.res is None or empty

        Returns:
            Subscriptions: create or update existing data from DB
        """
        if not self.res or self.res is None or len(self.res) == 0:
            raise ValueError("No data to save")
        for item in self.res:
            SubscriptionsModel.objects.update_or_create(
                subscription_id=item["subscription_id"], defaults=item
            )
        return self


class Marketplaces:
    """Azure API Marketplaces class to get data
    use Azure API ConsumptionManagementClient
    """

    def __init__(
        self, auth: Auth, subscription: SubscriptionsModel, date: dt = dt.now(ZoneInfo(TIME_ZONE))
    ) -> None:
        self.auth: Auth = auth
        self.subscription: SubscriptionsModel = subscription
        self.yearMonth: str = date.strftime("%Y%m")

    def get(self) -> "Marketplaces":
        """Get from Azure API

        Returns:
            Marketplaces: Azure API Marketplaces object
        """
        client = ConsumptionManagementClient(
            credential=self.auth.credential,
            subscription_id=self.subscription.subscription_id,
        )
        self.clientale = client.marketplaces
        self.res = self.clientale.list(
            scope=f"/subscriptions/{self.subscription.subscription_id}/providers/Microsoft.Billing/billingPeriods/{self.yearMonth}"
        )
        return self

    def db_save(self, ignore_conflicts: bool = False, update_conflicts: bool = True, check_conflic_on_create: bool = True) -> "Marketplaces":
        """Save data to DB

        Args:
            ignore_conflicts (bool, optional): Should DB ignore conficted data. Defaults to False.
            update_conflicts (bool, optional): Should DB update conflicted data. Defaults to True.
            check_conflic_on_create (bool, optional): If data confilcting should it be updated. Defaults to True.

        Returns:
            Marketplaces: Azure API Marketplaces object
        """
        def get_uuid(value):
            try:
                return str(uuid.UUID(value)) if value else None
            except ValueError:
                return None

        if self.res is None or not self.res:
            raise ValueError("No data to save")
        # This is not best practice but it works and I am lazy
        uniqueFields = ["usage_start", "instance_name",
                        "subscription_name", "publisher_name", "plan_name"]
        data: list[MarketplacesModel] = []
        for item in self.res:
            raw = item.as_dict() if hasattr(item, "as_dict") else vars(item)
            data.append(
                MarketplacesModel(
                    subscription=self.subscription,
                    source_id=get_uuid(value=raw.get("name")),
                    name=raw.get("id"),
                    type=raw.get("type"),
                    tags=raw.get("tags"),
                    billing_period_id=raw.get("billing_period_id"),
                    usage_start=raw.get("usage_start"),
                    usage_end=raw.get("usage_end"),
                    resource_rate=raw.get("resource_rate"),
                    offer_name=raw.get("offer_name"),
                    resource_group=raw.get("resource_group"),
                    additional_info=raw.get("additional_info"),
                    order_number=get_uuid(value=raw.get("order_number")),
                    instance_name=raw.get("instance_name"),
                    instance_id=raw.get("instance_id"),
                    currency=raw.get("currency"),
                    consumed_quantity=raw.get("consumed_quantity"),
                    unit_of_measure=raw.get("unit_of_measure"),
                    pretax_cost=raw.get("pretax_cost"),
                    is_estimated=raw.get("is_estimated"),
                    meter_id=raw.get("meter_id"),
                    subscription_name=raw.get("subscription_name"),
                    account_name=raw.get("account_name"),
                    department_name=raw.get("department_name"),
                    cost_center=raw.get("cost_center"),
                    publisher_name=raw.get("publisher_name"),
                    plan_name=raw.get("plan_name"),
                    is_recurring_charge=raw.get("is_recurring_charge"),
                )
            )
        if check_conflic_on_create:
            MarketplacesModel.objects.bulk_create(
                data, batch_size=500,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
                unique_fields=uniqueFields,
                update_fields=[col for col in MarketplacesModel._meta.get_fields(
                ) if col.name not in uniqueFields]
            )
        else:
            MarketplacesModel.objects.bulk_create(
                data, batch_size=500,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts
            )
        return self
