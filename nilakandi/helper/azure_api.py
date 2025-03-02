from re import sub
from datetime import datetime as dt, timedelta
import uuid
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
        self.token = self.credential.get_token("https://management.azure.com/.default")


class Services:
    """
    Azure API Services class to get data from Azure API
    """

    def __init__(
        self,
        auth: Auth,
        subscription: SubscriptionsModel,
        end_date: dt = dt.now(),
        start_date: dt | None = None,
    ) -> None:
        self.auth = auth
        self.subscription: SubscriptionsModel = subscription
        self.startDate = start_date if start_date else end_date - timedelta(days=7)
        self.endDate = end_date

    def get(self) -> "Services":
        """Get data from Azure API"""
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
                ],
            ),
        )
        self.clientale: QueryResult = client.query
        self.res = self.clientale.usage(scope=self.scope, parameters=self.query)
        return self

    def db_save(self) -> "Services":
        if not self.res or self.res is None:
            raise ValueError("No data to save")
        data: list[ServicesModel] = []
        cols = [
            sub(r"(?<!^)(?=[A-Z])", "_", col.name).lower() for col in self.res.columns
        ]
        cols[cols.index("cost_u_s_d")] = "cost_usd"
        for item in self.res.rows:
            if "usage_date" in cols and item[cols.index("usage_date")]:
                dateIs = dt.strptime(str(item[cols.index("usage_date")]), "%Y%m%d")
            else:
                dateIs = dt.now()
            data.append(
                ServicesModel(
                    subscription=self.subscription,
                    usage_date=dateIs,
                    charge_type=(
                        item[cols.index("charge_type")]
                        if "charge_type" in cols
                        else None
                    ),
                    service_name=(
                        item[cols.index("service_name")]
                        if "service_name" in cols
                        else None
                    ),
                    service_tier=(
                        item[cols.index("service_tier")]
                        if "service_tier" in cols
                        else None
                    ),
                    meter=item[cols.index("meter")] if "meter" in cols else None,
                    part_number=(
                        item[cols.index("part_number")]
                        if "part_number" in cols
                        else None
                    ),
                    cost_usd=(
                        item[cols.index("cost_usd")] if "cost_usd" in cols else None
                    ),
                    currency=(
                        item[cols.index("currency")] if "currency" in cols else None
                    ),
                )
            )
        ServicesModel.objects.bulk_create(data, batch_size=500)
        return self

    def __dict__(self) -> dict:
        return self.res.as_dict() if self.res else {}


class Subscriptions:
    """
    Subscriptions class to get all subscriptions from Azure API
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
            Subscriptions: Subscriptions object
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
    def __init__(
        self, auth: Auth, subscription: SubscriptionsModel, date: dt = dt.now()
    ) -> None:
        self.auth: Auth = auth
        self.subscription: SubscriptionsModel = subscription
        self.yearMonth: str = date.strftime("%Y%m")

    def get(self) -> "Marketplaces":
        client = ConsumptionManagementClient(
            credential=self.auth.credential,
            subscription_id=self.subscription.subscription_id,
        )
        self.clientale = client.marketplaces
        self.res = self.clientale.list(
            scope=f"/subscriptions/{self.subscription.subscription_id}/providers/Microsoft.Billing/billingPeriods/{self.yearMonth}"
        )
        return self

    def db_save(self) -> "Marketplaces":
        def get_uuid(value):
            try:
                return str(uuid.UUID(value)) if value else None
            except ValueError:
                return None

        if self.res is None or not self.res:
            raise ValueError("No data to save")
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
        MarketplacesModel.objects.bulk_create(data, batch_size=500)
        return self
