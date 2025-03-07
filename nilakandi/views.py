from django.conf import settings
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect, render

from nilakandi.models import Marketplace as MarketplacesModel
from nilakandi.models import Services as ServicesModel
from nilakandi.models import Subscription as SubscriptionsModel

from .helper.azure_api import Auth, Services, Subscriptions
from .helper.serve_data import SubsData

# Create your views here.


def home(request):
    print(request.user)
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
        "lastAdded": MarketplacesModel.objects.order_by("-added").first(),
        # .added.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return render(request=request, template_name="home.html", context=data)


def subscriptions(request):
    subs = SubscriptionsModel.objects.all()
    data = {
        "subs": subs,
        "field_names": [field.name for field in SubscriptionsModel._meta.fields],
    }
    print(request)
    return render(request, "subscriptions.html", context=data)


def subscription_details(request, subsId):
    def toHtml(data) -> str:
        if data.empty:
            return "<pre>No Data</pre>"
        return data.to_html(
            classes="table table-striped", float_format="{:,.8f}".format, na_rep="n/a"
        )

    try:
        sub = SubscriptionsModel.objects.get(subscription_id=subsId)
    except SubscriptionsModel.DoesNotExist:
        redirect("home")
        return None
    serveData = SubsData(sub=sub)
    data = {
        "subsName": sub.display_name,
        "pivotTable": {
            "Services": toHtml(serveData.service()),
            "Marketplaces": toHtml(serveData.marketplace()),
        },
    }
    return render(request=request, template_name="subsreport.html", context=data)


def services(request):
    services = ServicesModel.objects.all()
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
