from uuid import UUID

from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.conf import settings

from .models import Services, Marketplace
from .helper.serve_data import SubsData
from .helper.azure_api import Auth, Services, Subscriptions
from nilakandi.models import (
    Subscription as SubscriptionsModel,
    Marketplace as MarketplacesModel,
)

# Create your views here.


def home(request):
    data = {
        "user": "Admin",
        "countTable": [
            {
                "subsId": str(sub.subscription_id),
                "name": sub.display_name,
                "marketplace": sub.marketplace_set.count(),
                "service": sub.services_set.count(),
            }
            for sub in SubscriptionsModel.objects.all()
        ],
        "lastAdded": MarketplacesModel.objects.order_by("-added")
        .first()
        .added.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return render(request=request, template_name="home.html", context=data)


def subscription(request, subsId):
    try:
        sub = SubscriptionsModel.objects.get(subscription_id=subsId)
    except SubscriptionsModel.DoesNotExist:
        redirect("home")
    data = {
        "subsName": sub.display_name,
        "pivotTable": SubsData(sub=sub).pivot().to_html(classes="table table-striped"),
    }
    return render(request=request, template_name="subsreport.html", context=data)


def services(request):
    services = Services.objects.all()
    perPage = request.GET.get("perPage", 10)
    paginanator = Paginator(object_list=services, per_page=perPage)

    pageNumber = request.GET.get("page")
    pageObj = paginanator.get_page(pageNumber)
    context = {
        "page_obj": pageObj,
        "perPage": perPage,
        "field_names": [field.name for field in Services._meta.fields],
    }
    return render(request, "servicesCost.html", context)


def getSubcriptions(request):
    auth = Auth(
        client_id=settings.AZURE_CLIENT_ID,
        client_secret=settings.AZURE_CLIENT_SECRET,
        tenant_id=settings.AZURE_TENANT_ID,
    )
    subs = Subscriptions(auth=auth).get()
    subs.db_save()
    return JsonResponse({"data": subs.res})


def testAPI(request):
    subs = SubscriptionsModel.objects.all()
    print(subs.values())
    return JsonResponse({"data": [sub.display_name for sub in subs]}, safe=False)


def marketplace(request):
    subs = SubscriptionsModel.objects.all()
    for sub in subs:
        sub.objects.marketplace
