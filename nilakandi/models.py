import uuid
from django.db import models


class Subscription(models.Model):
    subscription_id = models.UUIDField(primary_key=True)
    id = models.CharField(primary_key=False, max_length=100, unique=True)
    display_name = models.CharField(max_length=64)
    state = models.CharField(max_length=16)
    subscription_policies = models.JSONField(
        null=True, default=dict, blank=True)
    authorization_source = models.CharField(max_length=32)
    additional_properties = models.JSONField(
        null=True, default=dict, blank=True)
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)


class Services(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        to=Subscription, to_field='subscription_id', on_delete=models.RESTRICT, default=uuid.uuid4)
    usage_date = models.DateField()
    charge_type = models.CharField(max_length=16)
    service_name = models.CharField(max_length=128)
    service_tier = models.CharField(max_length=128)
    meter = models.CharField(max_length=128)
    part_number = models.CharField(max_length=10)
    cost_usd = models.FloatField()
    currency = models.CharField(max_length=4)
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)


class Operation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=64)
    type = models.CharField(max_length=64)
    status = models.CharField(max_length=64)
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
        to=Subscription, to_field='subscription_id', on_delete=models.RESTRICT, default=uuid.uuid4, db_comment="Originally called subscription_guid")
    source_id = models.UUIDField(
        default=uuid.uuid4, editable=True, null=True, db_comment="Originally called name")
    name = models.CharField(max_length=255, db_comment="Originally called id")
    type = models.CharField(max_length=255)
    tags = models.JSONField(null=True, default=dict, blank=True)
    billing_period_id = models.CharField(max_length=255)
    usage_start = models.DateTimeField()
    usage_end = models.DateTimeField()
    resource_rate = models.FloatField()
    offer_name = models.CharField(max_length=255)
    resource_group = models.CharField(max_length=255)
    additional_info = models.JSONField(null=True, default=dict, blank=True)
    order_number = models.UUIDField(
        default=uuid.uuid4, editable=True, null=True, blank=True)
    instance_name = models.CharField(max_length=255, null=True)
    instance_id = models.CharField(max_length=255, null=True)
    currency = models.CharField(max_length=4, default="USD")
    consumed_quantity = models.FloatField()
    unit_of_measure = models.CharField(max_length=255)
    pretax_cost = models.FloatField()
    is_estimated = models.BooleanField()
    meter_id = models.CharField(max_length=255, null=True)
    subscription_name = models.CharField(max_length=255)
    account_name = models.CharField(max_length=255)
    department_name = models.CharField(max_length=255)
    cost_center = models.CharField(max_length=255, null=True)
    publisher_name = models.CharField(max_length=255)
    plan_name = models.CharField(max_length=255)
    is_recurring_charge = models.BooleanField()
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)
