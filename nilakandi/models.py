import uuid
from enum import Enum

from django.contrib.postgres.fields import DateTimeRangeField
from django.db import models


class Subscription(models.Model):
    """
    Subscription model representing a subscription entity.

    Attributes:
        subscription_id (UUIDField): Primary key, unique identifier for the subscription.
        id (CharField): Unique identifier for the subscription, max length of 100 characters.
        display_name (CharField): Display name of the subscription.
        state (CharField): State of the subscription.
        subscription_policies (JSONField): JSON field to store subscription policies, can be null or blank, defaults to an empty dictionary.
        authorization_source (CharField): Source of authorization for the subscription.
        additional_properties (JSONField): JSON field to store additional properties, can be null or blank, defaults to an empty dictionary.
        last_edited (DateTimeField): Timestamp of the last edit, automatically updated.
        added (DateTimeField): Timestamp of when the subscription was added, automatically set and not editable.

    Methods:
        __str__: Returns the display name of the subscription.

    Meta:
        unique_together: Ensures that the combination of subscription_id, id, and display_name is unique.
    """

    subscription_id = models.UUIDField(primary_key=True)
    id = models.CharField(primary_key=False, max_length=100, unique=True)
    display_name = models.CharField()
    state = models.CharField()
    subscription_policies = models.JSONField(null=True, default=dict, blank=True)
    authorization_source = models.CharField()
    additional_properties = models.JSONField(null=True, default=dict, blank=True)
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)

    def __str__(self):
        return self.display_name

    class Meta:
        unique_together = ["subscription_id", "id", "display_name"]


class Services(models.Model):
    """
    Represents a service usage record in the system.

    Attributes:
        id (UUIDField): The unique identifier for the service record.
        subscription (ForeignKey): The subscription associated with the service usage.
        usage_date (DateField): The date when the service was used.
        charge_type (CharField): The type of charge for the service.
        service_name (CharField): The name of the service.
        service_tier (CharField): The tier of the service.
        meter (CharField): The meter associated with the service usage.
        part_number (CharField): The part number of the service.
        billing_month (DateField): The billing month for the service usage.
        resource_id (CharField, optional): The resource ID associated with the service usage.
        resource_type (CharField, optional): The type of resource associated with the service usage.
        cost_usd (FloatField): The cost of the service usage in USD.
        currency (CharField): The currency of the cost.
        last_edited (DateTimeField): The timestamp when the record was last edited.
        added (DateTimeField): The timestamp when the record was added.

    Methods:
        __str__: Returns the string representation of the service record.

    Meta:
        unique_together: Ensures that the combination of subscription, usage_date, service_name, resource_id, service_tier, and meter is unique.
    """

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

    def __str__(self):
        return self.id

    class Meta:
        unique_together = [
            "subscription",
            "usage_date",
            "service_name",
            "resource_id",
            "service_tier",
            "meter",
        ]


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

    def __str__(self):
        return self.name


class Marketplace(models.Model):
    """
    Marketplace model representing various attributes related to a marketplace subscription.

    Attributes:
        id (UUIDField): Primary key for the Marketplace model.
        subscription (ForeignKey): Foreign key to the Subscription model, originally called subscription_guid.
        source_id (UUIDField): UUID field originally called name.
        name (CharField): Name of the marketplace, originally called id.
        type (CharField): Type of the marketplace.
        tags (JSONField): JSON field to store tags, default is an empty dictionary.
        billing_period_id (CharField): ID of the billing period.
        usage_start (DateTimeField): Start time of the usage period.
        usage_end (DateTimeField): End time of the usage period.
        resource_rate (FloatField): Rate of the resource.
        offer_name (CharField): Name of the offer.
        resource_group (CharField): Name of the resource group.
        additional_info (JSONField): JSON field to store additional information, default is an empty dictionary.
        order_number (UUIDField): UUID field for the order number.
        instance_name (CharField): Name of the instance.
        instance_id (CharField): ID of the instance.
        currency (CharField): Currency used, default is "USD".
        consumed_quantity (FloatField): Quantity consumed.
        unit_of_measure (CharField): Unit of measure.
        pretax_cost (FloatField): Pre-tax cost.
        is_estimated (BooleanField): Indicates if the cost is estimated.
        meter_id (CharField): ID of the meter.
        subscription_name (CharField): Name of the subscription.
        account_name (CharField): Name of the account.
        department_name (CharField): Name of the department.
        cost_center (CharField): Name of the cost center.
        publisher_name (CharField): Name of the publisher.
        plan_name (CharField): Name of the plan.
        is_recurring_charge (BooleanField): Indicates if the charge is recurring.
        last_edited (DateTimeField): Timestamp of the last edit, auto-updated.
        added (DateTimeField): Timestamp when the record was added, auto-updated and not editable.

    Methods:
        __str__: Returns the name of the marketplace.

    Meta:
        unique_together: Ensures uniqueness for the combination of subscription, source_id, name, usage_start, billing_period_id, and instance_id.
    """

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

    def __str__(self):
        return self.name

    class Meta:
        unique_together = [
            "subscription",
            "source_id",
            "name",
            "usage_start",
            "billing_period_id",
            "instance_id",
        ]


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


class VirtualMachineCost(models.Model):
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

    """
        Constraint unique keys based on 
    """

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["billing_month", "resource_id", "meter_id"],
                name="unique_billing_resource_meter",
            )
        ]


class ExecTypeEnum(Enum):
    """
    ExecTypeEnum is an enumeration that defines the types of execution modes available.

    Attributes:
        ON_DEMAND (str): Represents an execution mode that is triggered manually.
        SCHEDULED (str): Represents an execution mode that is triggered based on a schedule.
    """

    ON_DEMAND = "OnDemand"
    SCHEDULED = "Scheduled"


class ExecStatusEnum(Enum):
    """
    ExecStatusEnum is an enumeration that represents the various execution statuses
    that a process or task can have.

    Attributes:
        COMPLETED (str): Indicates that the task has been completed successfully.
        DATA_NOT_AVAILABLE (str): Indicates that the required data is not available.
        FAILED (str): Indicates that the task has failed.
        IN_PROGRESS (str): Indicates that the task is currently in progress.
        NEW_DATA_NOT_AVAILABLE (str): Indicates that new data required for the task is not available.
        QUEUED (str): Indicates that the task is queued and waiting to be processed.
        TIMEOUT (str): Indicates that the task has timed out.
    """

    COMPLETED = "Completed"
    DATA_NOT_AVAILABLE = "DataNotAvailable"
    FAILED = "Failed"
    IN_PROGRESS = "InProgress"
    NEW_DATA_NOT_AVAILABLE = "NewDataNotAvailable"
    QUEUED = "Queued"
    TIMEOUT = "Timeout"


class ExportHistory(models.Model):
    """
    Model representing the export history of a subscription.

    Attributes:
        id (UUIDField): Primary key, originally called name.
        subscription (ForeignKey): Foreign key to Subscription model, referencing subscription_id.
        exec_string (CharField): Unique execution string, originally called id.
        blobs_path (CharField): Path to blobs, originally called properties.manifestFile.
        exec_type (CharField): Type of execution, originally called properties.executionType.
        exec_status (CharField): Status of execution, originally called properties.status.
        submitted (DateTimeField): Submission time, originally called properties.submittedTime.
        proc_start_time (DateTimeField): Processing start time, originally called properties.processingStartTime.
        proc_end_time (DateTimeField): Processing end time, originally called properties.processingEndTime.
        report_datetime_range (DateTimeRangeField): Date range for the report, originally called properties.startDate & properties.endDate.
        run_settings (HStoreField): Run settings, originally called properties.runSettings.
        last_edited (DateTimeField): Timestamp of the last edit, auto-updated.
        added (DateTimeField): Timestamp of when the record was added, auto-updated and not editable.

    Methods:
        __str__: Returns a string representation of the export history, including subscription name and report date range.

    Meta:
        required_db_vendor: Specifies that the required database vendor is PostgreSQL.
        unique_together: Ensures that the combination of subscription and exec_string is unique.
        indexes: Defines indexes on exec_status and submitted, exec_type and submitted, and exec_type, exec_status, and submitted.
    """

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, db_comment="Originally called name"
    )
    subscription = models.ForeignKey(
        to=Subscription,
        to_field="subscription_id",
        on_delete=models.RESTRICT,
    )
    exec_string = models.CharField(
        unique=True,
        verbose_name="Execution String",
        db_comment="Originally called id",
    )
    blobs_path = models.CharField(
        db_comment="Originally called properties.manifestFile",
    )
    exec_type = models.CharField(
        choices=[(e.value, e.name) for e in ExecTypeEnum],
        db_comment="Originally called properties.executionType",
    )
    exec_status = models.CharField(
        choices=[(e.value, e.name) for e in ExecStatusEnum],
        db_comment="Originally called properties.status",
    )
    submitted = models.DateTimeField(
        db_comment="Originally called properties.submittedTime"
    )
    proc_start_time = models.DateTimeField(
        null=True,
        blank=True,
        db_comment="Originally called properties.processingStartTime",
    )
    proc_end_time = models.DateTimeField(
        null=True,
        blank=True,
        db_comment="Originally called properties.processingEndTime",
    )
    report_datetime_range = DateTimeRangeField(
        db_comment="Originally called properties.startDate & properties.endDate"
    )
    run_settings = models.JSONField(
        default=dict,
        db_comment="Originally called properties.runSettings",
    )
    last_edited = models.DateTimeField(auto_now=True)
    added = models.DateTimeField(auto_now=True, editable=False)

    def __str__(self):
        start, end = self.report_datetime_range.lower, self.report_datetime_range.upper
        return f"{self.subscription} - {start} to {end}"

    class Meta:
        required_db_vendor = "postgresql"
        unique_together = ["subscription", "exec_string"]
        indexes = [
            models.Index(fields=["exec_status", "submitted"]),
            models.Index(fields=["exec_type", "submitted"]),
            models.Index(fields=["exec_type", "exec_status", "submitted"]),
        ]
