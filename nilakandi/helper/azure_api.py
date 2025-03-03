from typing import Iterable
import uuid
import requests

from pandas import DataFrame, notna, to_datetime
from re import sub
from datetime import datetime as dt, timedelta
from zoneinfo import ZoneInfo

from azure.identity import ClientSecretCredential
from azure.mgmt.consumption import ConsumptionManagementClient
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.consumption.operations import MarketplacesOperations
from azure.mgmt.consumption.models import MarketplacesListResult
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
        self.token = self.credential.get_token("https://management.azure.com/.default")


class Services:
    """Azure API Services class to get data from Azure API"""

    def __init__(
        self,
        auth: Auth,
        subscription: SubscriptionsModel,
        end_date: dt = dt.now(ZoneInfo(TIME_ZONE)),
        start_date: dt | None = None,
    ) -> None:
        self.auth = auth
        self.subscription: SubscriptionsModel = subscription
        self.startDate = start_date if start_date else end_date - timedelta(days=7)
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
            scope=self.scope, parameters=self.query
        )
        self.nextLink: str = self.queryRes.next_link
        self.res: DataFrame = DataFrame(
            data=self.queryRes.rows,
            columns=[
                sub(
                    r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", col.name
                ).lower()
                for col in self.queryRes.columns
            ],
        )
        return self

    def next(self, next_uri: str | None = None) -> "Services":
        if (not self.nextLink) or (self.nextLink is None):
            raise ValueError("No next link")
        payload = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {
                "from": self.query.time_period.as_dict()["from_property"],
                "to": self.query.time_period.as_dict()["to"],
            },
            "dataset": self.query.dataset.as_dict(),
        }
        try:
            apiRes = requests.post(
                url=self.nextLink if not next_uri else next_uri,
                headers={
                    "Authorization": f"Bearer {self.auth.token.token}",
                    "Content-Type": "application/json",
                    "User-Agent": str(
                        self.clientale._config.user_agent_policy._user_agent
                    ),
                },
                json=payload,
            )
            apiRes.raise_for_status()
        except requests.HTTPError as e:
            raise e
        next_res = apiRes.json()
        self.nextLink: str = next_res["properties"]["nextLink"]
        self.res: DataFrame = DataFrame(
            next_res["properties"]["rows"],
            columns=[
                sub(
                    r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", col["name"]
                ).lower()
                for col in next_res["properties"]["columns"]
            ],
        )
        # self.res['usage_date'] = to_datetime(self.res['usage_date'].astype(
        #     str), format="%Y%m%d")
        return self

    def db_save(
        self,
        ignore_conflicts: bool = False,
        update_conflicts: bool = True,
        check_conflic_on_create: bool = True,
    ) -> "Services":
        """Save data to DB

        Args:
            ignore_conflicts (bool, optional): Should DB ignore conficted data. Defaults to False.
            update_conflicts (bool, optional): Should DB update conflicted data. Defaults to True.
            check_conflic_on_create (bool, optional): If data confilcting should it be updated. Defaults to True.

        Returns:
            Services: Azure API Services object
        """
        if not isinstance(self.res, DataFrame) or self.res.empty:
            print(f"Data: {self.res.head(5)}")
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
            for index, row in self.res.iterrows()
        ]
        if check_conflic_on_create:
            ServicesModel.objects.bulk_create(
                data,
                batch_size=500,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
                unique_fields=["usage_date", "service_name", "service_tier", "meter"],
                update_fields=["charge_type", "part_number", "cost_usd", "currency"],
            )
        else:
            ServicesModel.objects.bulk_create(data, batch_size=500)
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
        self,
        auth: Auth,
        subscription: SubscriptionsModel,
        date: dt = dt.now(ZoneInfo(TIME_ZONE)),
    ) -> None:
        self.auth: Auth = auth
        self.subscription: SubscriptionsModel = subscription
        self.yearMonth: str = date.strftime("%Y%m")

    def get(self) -> "Marketplaces":
        """Get from Azure API

        Returns:
            Marketplaces: Azure API Marketplaces object
        """
        client: ConsumptionManagementClient = ConsumptionManagementClient(
            credential=self.auth.credential,
            subscription_id=self.subscription.subscription_id,
        )
        self.clientale: MarketplacesOperations = client.marketplaces
        self.res: Iterable[MarketplacesListResult] = self.clientale.list(
            scope=f"/subscriptions/{self.subscription.subscription_id}/providers/Microsoft.Billing/billingPeriods/{self.yearMonth}"
        )
        return self

    def db_save(
        self,
        ignore_conflicts: bool = False,
        update_conflicts: bool = True,
        check_conflic_on_create: bool = True,
    ) -> "Marketplaces":
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
        uniqueFields = [
            "usage_start",
            "instance_name",
            "subscription_name",
            "publisher_name",
            "plan_name",
        ]
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
                data,
                batch_size=500,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
                unique_fields=uniqueFields,
                update_fields=[
                    col
                    for col in MarketplacesModel._meta.get_fields()
                    if col.name not in uniqueFields
                ],
            )
        else:
            MarketplacesModel.objects.bulk_create(
                data,
                batch_size=500,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
            )
        return self


class VirtualMachines:
    def __init__(self, auth: Auth, subscription: SubscriptionsModel) -> None:
        """Class Initializer

        Args:
            auth (Auth): Auth object
            subscription (SubscriptionsModel): Subscription object
        """
        self.auth = auth
        self.subscription: SubscriptionsModel = subscription

    # TODO : Implement Best Practice
    def get_all(self):
        """Get All VM based on Subscription from Azure API

        Returns:
            VirtualMachine: Azure API VirtualMachine and VirtualMachine Billing object
        """
        client: ComputeManagementClient = ComputeManagementClient(
            credential=self.auth.credential,
            subscription_id=self.subscription.subscription_id,
        )

        vm_data = []

        vms = client.virtual_machines.list_all()

        for vm in vms:

            # TODO : Append to Model
            extracted_data = {
                "name": vm.name,
                "tags": vm.tags,
                "resource_group": vm.id,
                "location": vm.location,
                "vm_id": vm.vm_id,
                "provisioning_state": vm.provisioning_state,
                "hardware_profile_vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else None,
                "image_reference_publisher": vm.storage_profile.image_reference.publisher if vm.storage_profile and vm.storage_profile.image_reference else None,
                "image_reference_offer": vm.storage_profile.image_reference.offer if vm.storage_profile and vm.storage_profile.image_reference else None,
                "image_reference_sku": vm.storage_profile.image_reference.sku if vm.storage_profile and vm.storage_profile.image_reference else None,
                "image_reference_version": vm.storage_profile.image_reference.version if vm.storage_profile and vm.storage_profile.image_reference else None,
                "os_disk_name": vm.storage_profile.os_disk.name if vm.storage_profile and vm.storage_profile.os_disk else None,
                "os_disk_caching": vm.storage_profile.os_disk.caching if vm.storage_profile and vm.storage_profile.os_disk else None,
                "os_disk_create_option": vm.storage_profile.os_disk.create_option if vm.storage_profile and vm.storage_profile.os_disk else None,
                "os_disk_managed_disk_id": vm.storage_profile.os_disk.managed_disk.id if vm.storage_profile and vm.storage_profile.os_disk and vm.storage_profile.os_disk.managed_disk else None,
                "os_disk_managed_disk_storage_account_type": vm.storage_profile.os_disk.managed_disk.storage_account_type if vm.storage_profile and vm.storage_profile.os_disk and vm.storage_profile.os_disk.managed_disk else None,
                "os_disk_size_gb": vm.storage_profile.os_disk.disk_size_gb if vm.storage_profile and vm.storage_profile.os_disk else None,
                "os_disk_delete_option": vm.storage_profile.os_disk.delete_option if vm.storage_profile and vm.storage_profile.os_disk else None,
                "data_disks": vm.storage_profile.data_disks if  vm.storage_profile.data_disks else None,
                "computer_name": vm.os_profile.computer_name if vm.os_profile else None,
                "admin_username": vm.os_profile.admin_username if vm.os_profile else None,
                "network_interfaces_ids": ", ".join([nic.id for nic in vm.network_profile.network_interfaces]) if vm.network_profile and vm.network_profile.network_interfaces else None,
                "boot_diagnostics_enabled": vm.diagnostics_profile.boot_diagnostics.enabled if vm.diagnostics_profile and vm.diagnostics_profile.boot_diagnostics else None,
                "boot_diagnostics_storage_uri": vm.diagnostics_profile.boot_diagnostics.storage_uri if vm.diagnostics_profile and vm.diagnostics_profile.boot_diagnostics else None,
                "identity_type": vm.identity.type if vm.identity else None,
                "zones": vm.zones if vm.zones else None,
                "plan_name": vm.plan.name if vm.plan else None,
                "availability_set_id": vm.availability_set.id if vm.availability_set else None,
                "virtual_machine_scale_set_id": vm.virtual_machine_scale_set.id if vm.virtual_machine_scale_set else None,
                "proximity_placement_group_id": vm.proximity_placement_group.id if vm.proximity_placement_group else None,
                "priority": vm.priority,
                "eviction_policy": vm.eviction_policy,
                "license_type": vm.license_type,
                "host_id": vm.host.id if vm.host else None,
                "host_group_id": vm.host_group.id if vm.host_group else None,
                "extensions_time_budget": vm.extensions_time_budget,
                "platform_fault_domain": vm.platform_fault_domain,
            }
            vm_data.append(extracted_data)

        return self

    # TODO : Implement Best Practice
    def get_virtual_machine_billing(self, months):
        """Get Virtual Machine Billing Data from Azure API

        Returns:
            VirtualMachine: Azure API VirtualMachine and VirtualMachine Billing object
        """
        client: CostManagementClient = CostManagementClient(
            credential=self.auth.credential,
            subscription_id=self.subscription.subscription_id,
        )

        required_columns = [
            "BillingMonth",
            "ResourceId",
            "ResourceType",
            "ResourceGroup",
            "ServiceName",
            "ResourceGroupName",
            "ResourceLocation",
            "ConsumedService",
            "MeterId",
            "MeterCategory",
            "MeterSubcategory",
            "Meter",
            "DepartmentName",
            "SubscriptionId",
            "SubscriptionName",
        ]
        
        start_date, end_date = months
        
        time_period = QueryTimePeriod(
            from_property=start_date,  # Convert datetime to ISO format
            to=end_date,  # Convert datetime to ISO format
        )
        
        dataset = QueryDataset(
            granularity="None",
            aggregation={"totalCost": QueryAggregation(name="PreTaxCost", function="Sum")},
            grouping=[QueryGrouping(type="Dimension", name=column) for column in required_columns],
        )
        
        query_parameters = QueryDefinition(
            timeframe="Custom",
            time_period=time_period,
            dataset=dataset,
            type="Usage",
        )
        
        query_result = client.query.usage(
            scope=f"/subscriptions/{self.subscription.subscription_id}/", parameters=query_parameters
        )
        
        query_result_columns = [column.name for column in query_result.columns]
        
        self.res: DataFrame = DataFrame(
            data=query_result.rows,
            columns=[name for name in query_result_columns]
        )

        return self
    
    # TODO : Pass this function to get virtual machine billing (Based on debug, we need another function to get the billing range)
    def months_function():
        ...

    # TODO : Not sure what to do in this function
    def db_save(self):
        """Save Data to DB

        Raises:
            ValueError: self.res is None or empty

        Returns:
            VirtualMachine: create or update existing data from DB
        """

        def get_uuid(value):
            try:
                return str(uuid.UUID(value)) if value else None
            except ValueError:
                return None

        if self.res is None or not self.res:
            raise ValueError("No data to save")
