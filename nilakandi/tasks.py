from celery import shared_task

from nilakandi.models import Subscription as SubscriptionsModel
from nilakandi.helper import azure_api as azi
from datetime import datetime as dt, timezone, timedelta


@shared_task
def grab_services(auth: azi.Auth, sub: SubscriptionsModel, start_date: dt, end_date: dt) -> None:
    loopedDate = start_date
    deltaDays: int = 3 if (
        end_date - start_date).days > 3 else (end_date - start_date).days
    while loopedDate <= end_date:
        tempDate = loopedDate + timedelta(days=deltaDays)
        services = azi.Services(
            auth=auth,
            subscription=sub,
            start_date=loopedDate,
            end_date=tempDate,
        )
        services.get().db_save()
        loopedDate += timedelta(days=deltaDays+1)
