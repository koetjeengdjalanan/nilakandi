from datetime import datetime
from uuid import UUID

from django import forms
from django.conf import settings

from nilakandi.models import Subscription as SubscriptionsModel


class ReportForm(forms.Form):
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
            ("upload", "BYOF!"),
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
