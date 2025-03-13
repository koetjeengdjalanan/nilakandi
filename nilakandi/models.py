import uuid
import datetime
from django.db import models


class Subscription(models.Model):
    subscription_id = models.UUIDField(primary_key=True)
    id = models.CharField(primary_key=False, max_length=100, unique=True)
    display_name = models.CharField()
    state = models.CharField()
    subscription_policies = models.JSONField(null=True, default=dict, blank=True)
    authorization_source = models.CharField()
    additional_properties = models.JSONField(null=True, default=dict, blank=True)
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)

class Services(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        to=Subscription,
        to_field="subscription_id",
        on_delete=models.RESTRICT,
        default=uuid.uuid4,
    )
    usage_date = models.DateField()
    charge_type = models.CharField()
    service_name = models.CharField()
    service_tier = models.CharField()
    meter = models.CharField()
    part_number = models.CharField()
    billing_month = models.DateField()
    resource_id = models.CharField(null=True)
    resource_type = models.CharField(null=True)
    cost_usd = models.FloatField()
    currency = models.CharField()
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)


class Operation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField()
    type = models.CharField()
    status = models.CharField()
    started = models.DateTimeField()
    completed = models.DateTimeField()
    duration = models.DurationField()
    error = models.JSONField(null=True, default=dict, blank=True)
    output = models.JSONField(null=True, default=dict, blank=True)
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)


class Marketplace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        to=Subscription,
        to_field="subscription_id",
        on_delete=models.RESTRICT,
        default=uuid.uuid4,
        db_comment="Originally called subscription_guid",
    )
    source_id = models.UUIDField(
        default=uuid.uuid4,
        editable=True,
        null=True,
        db_comment="Originally called name",
    )
    name = models.CharField(db_comment="Originally called id")
    type = models.CharField()
    tags = models.JSONField(null=True, default=dict, blank=True)
    billing_period_id = models.CharField()
    usage_start = models.DateTimeField()
    usage_end = models.DateTimeField()
    resource_rate = models.FloatField()
    offer_name = models.CharField()
    resource_group = models.CharField()
    additional_info = models.JSONField(null=True, default=dict, blank=True)
    order_number = models.UUIDField(
        default=uuid.uuid4, editable=True, null=True, blank=True
    )
    instance_name = models.CharField(null=True)
    instance_id = models.CharField(null=True)
    currency = models.CharField(default="USD")
    consumed_quantity = models.FloatField()
    unit_of_measure = models.CharField()
    pretax_cost = models.FloatField()
    is_estimated = models.BooleanField()
    meter_id = models.CharField(null=True)
    subscription_name = models.CharField()
    account_name = models.CharField()
    department_name = models.CharField()
    cost_center = models.CharField(null=True)
    publisher_name = models.CharField()
    plan_name = models.CharField()
    is_recurring_charge = models.BooleanField()
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)


class VirtualMachine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        to=Subscription,
        to_field="subscription_id",
        on_delete=models.RESTRICT,
        default=uuid.uuid4,
    )
    vm_subs_id = models.CharField(null=True)
    name = models.CharField(null=True)
    type = models.CharField(null=True)
    location = models.CharField(null=True)
    tags = models.JSONField(null=True, default=dict, blank=True)
    resources = models.JSONField(null=True, default=dict, blank=True)
    identity = models.JSONField(null=True, default=dict, blank=True)
    zones = models.JSONField(null=True, default=list, blank=True)
    etag = models.CharField(null=True)
    hardware_profile = models.JSONField(null=True, default=dict, blank=True)
    storage_profile = models.JSONField(null=True, default=dict, blank=True)
    os_profile = models.JSONField(null=True, default=dict, blank=True)
    network_profile = models.JSONField(null=True, default=dict, blank=True)
    diagnostic_profile = models.JSONField(null=True, default=dict, blank=True)
    provisioning_state = models.CharField(null=True)
    license_type = models.CharField(null=True)
    vm_id = models.CharField(null=True)
    time_created = models.TimeField(null=True)
    security_profile = models.JSONField(null=True, default=dict, blank=True)
    additional_capabilities = models.JSONField(null=True, default=dict, blank=True)
    plan = models.JSONField(null=True, default=dict, blank=True)
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)


class Billing(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        to=Subscription,
        to_field="subscription_id",
        on_delete=models.RESTRICT,
        default=uuid.uuid4,
    )
    resource_id = models.CharField(null=True)
    resource_type = models.CharField()
    resource_group = models.CharField()
    service_name = models.CharField()
    resource_group_name = models.CharField()
    resource_location = models.CharField()
    consumed_service = models.CharField()
    meter_id = models.CharField()
    meter_category = models.CharField()
    meter_sub_category = models.CharField()
    meter = models.CharField()
    department_name = models.CharField()
    subscription_name = models.CharField()
    currency = models.CharField()
    billing_month = models.DateField()
    pretax_cost = models.FloatField()
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)