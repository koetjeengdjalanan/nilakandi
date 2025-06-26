from datetime import datetime
from uuid import UUID

from django import forms
from django.conf import settings

from nilakandi.models import Subscription as SubscriptionsModel


class ReportForm(forms.Form):
    """
    A Django form for configuring and generating various Azure-related reports.

    This form allows users to specify parameters for report generation, including
    the data source, subscription, report type, date range, and decimal precision.

    Fields:
        data_source: Source of the report data (local database or Azure)
        subscription: The Azure subscription to report on
        report_type: Type of report to generate (summary, services, marketplaces, etc.)
        from_date: Start date for the report period (defaults to earliest available data)
        to_date: End date for the report period (defaults to current date)
        decimal_count: Number of decimal places for numeric values (defaults to 8)
    """

    SUB_CHOICES: list[tuple[None | UUID, str]] = [
        (None, "-- Select Subscription --"),
    ]
    for sub in SubscriptionsModel.objects.all():
        SUB_CHOICES.append((sub.pk, sub.display_name))

    REPORT_TYPES: list[tuple[str, str]] = [
        (None, "-- Select Report Type --"),
        ("summary", "Summary"),
        ("services", "Services"),
        ("marketplaces", "Marketplaces"),
        ("virtualmachines", "Virtual Machines"),
    ]

    data_source = forms.ChoiceField(
        label="Data Source",
        choices=[
            ("db", "From Local Database"),
            ("azure", "Straight from Azure"),
        ],
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    subscription = forms.ChoiceField(
        label="Subscription",
        choices=SUB_CHOICES,
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    report_type = forms.ChoiceField(
        label="Report Type",
        choices=REPORT_TYPES,
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    from_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        initial=datetime.strptime(settings.EARLIEST_DATA, "%Y%m%d"),
    )
    to_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        initial=datetime.today(),
    )
    decimal_count = forms.IntegerField(
        max_value=16,
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        initial=8,
    )


class MultipleFileInput(forms.FileInput):
    """
    A file input widget that allows for multiple file selection.

    This widget extends Django's FileInput by enabling the 'multiple' attribute
    on the rendered HTML input element, allowing users to select multiple files
    in the file dialog.

    Example:
        ```python
        class UploadForm(forms.Form):
            files = forms.FileField(widget=MultipleFileInput())
        ```

    Attributes:
        allow_multiple_selected (bool): When True, enables multiple file selection
            in the browser's file dialog.
    """

    allow_multiple_selected = True


class UploadRawData(forms.Form):
    """
    A Django form for uploading raw data files with a report type selection.

    This form allows users to select a report type from predefined options
    and upload one or more files associated with that report type.

    Attributes:
        REPORT_TYPES (list[tuple[str, str]]): Available report type options as (value, display_name) pairs.
        report_type (forms.ChoiceField): Field for selecting the report type.
        files (forms.FileField): Field for uploading multiple files.

    Notes:
        The files field is marked as not required to provide flexibility in the upload process.
        The available report types include Summary, Services, Marketplaces, and Virtual Machines.
    """

    REPORT_TYPES: list[tuple[str, str]] = [
        (None, "-- Select Report Type --"),
        ("summary", "Summary"),
        ("services", "Services"),
        ("marketplaces", "Marketplaces"),
        ("virtualmachines", "Virtual Machines"),
    ]

    report_type = forms.ChoiceField(
        label="Report Type",
        choices=REPORT_TYPES,
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    files = forms.FileField(
        widget=MultipleFileInput(),
        label="Select files to upload",
        required=False,  # Important for flexibility
    )
