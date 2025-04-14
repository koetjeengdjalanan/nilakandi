from django.conf import settings
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from nilakandi.models import HtmxTest as HtmxTestModel
from nilakandi.models import Marketplace as MarketplacesModel
from nilakandi.models import Services as ServicesModel
from nilakandi.models import Subscription as SubscriptionsModel

from .helper.azure_api import Auth, Services, Subscriptions
from .helper.serve_data import SubsData

"""
    Views are the functions that handle the requests and return the responses.
    The views are the functions that Django calls when a user requests a page from your website.
    Views are the place where you put the "logic" of your application.
    Each view is responsible for doing one of two things: returning an HttpResponse object containing the content for the requested page, or raising an exception such as Http404.
"""


def home(request):
    """Home Page View

    Args:
        request : The HTTP Request

    Returns:
        render: render the request, with defined template file  and context
    """

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
    return render(request=request, template_name="base/home/home.html", context=data)


def subscriptions(request):
    """Subscription Page View

    Args:
        request : The HTTP Request

    Returns:
        render: render the request, with defined template file  and context
    """
    subs = SubscriptionsModel.objects.all()
    data = {
        "subs": subs,
        "field_names": [field.name for field in SubscriptionsModel._meta.fields],
    }
    print(request)
    return render(
        request, template_name="base/subscriptions/subscriptions.html", context=data
    )


def subscriptions_detail(request, subsId):
    subscription = get_object_or_404(SubscriptionsModel, subscription_id=subsId)
    context = {"subscription": subscription}
    return render(request, "base/subscriptions/subscription_details.html", context)


def subscription_details(request, subsId):
    """Subscription Detail Page View

    Args:
        request : The HTTP Request
        subsId : Subscription ID

    Returns:
        render: render the request, with defined template file  and context
    """

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
    return render(
        request=request,
        template_name="base/subscription_reports/subsreport.html",
        context=data,
    )


def services(request):
    """Services Page View

    Args:
        request : The HTTP Request

    Returns:
        render: render the request, with defined template file  and context
    """

    services = ServicesModel.objects.all()
    perPage = request.GET.get("perPage", 10)
    paginanator = Paginator(object_list=services, per_page=perPage)

    pageNumber = request.GET.get("page")
    pageObj = paginanator.get_page(pageNumber)
    data = {
        "page_obj": pageObj,
        "perPage": perPage,
        "field_names": [field.name for field in Services._meta.fields],
    }
    return render(request, template_name="base/services/services.html", context=data)


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


"""
This code below are related to HTMX Page
"""


def htmx_example(request):
    items = HtmxTestModel.objects.all()
    return render(request, "htmxExample.html", {"items": items})


def htmx_list(request):
    items = HtmxTestModel.objects.all()
    return render(request, "partials/htmx/htmxList.html", {"items": items})


def htmx_test_create(request):
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description")
        HtmxTestModel.objects.create(name=name, description=description)
        return HttpResponse(status=204, headers={"HX-Trigger": "itemListChanged"})
    return HttpResponse(status=400)


def htmx_create_modal(request):
    return render(request, "partials/htmx/htmxForm.html")


def htmx_test_update(request, pk):
    item = get_object_or_404(HtmxTestModel, pk=pk)
    if request.method == "POST":
        item.name = request.POST.get("name")
        item.description = request.POST.get("description")
        item.save()
        return HttpResponse(status=204, headers={"HX-Trigger": "itemListChanged"})
    return HttpResponse(status=400)


def htmx_update_modal(request, pk):
    item = get_object_or_404(HtmxTestModel, pk=pk)
    return render(request, "partials/htmx/htmxForm.html", {"item": item})


def htmx_test_delete(request, pk):
    item = get_object_or_404(HtmxTestModel, pk=pk)
    item.delete()
    return HttpResponse(status=204, headers={"HX-Trigger": "itemListChanged"})
