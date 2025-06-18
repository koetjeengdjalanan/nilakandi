from django.conf import settings
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from nilakandi.models import Marketplace as MarketplacesModel
from nilakandi.models import Services as ServicesModel
from nilakandi.models import Subscription as SubscriptionsModel

from .helper.azure_api import Auth, Services, Subscriptions
from .helper.miscellaneous import df_tohtml
from .helper.serve_data import SubsData


def home(request):
    from nilakandi.forms import ReportForm
    from nilakandi.models import GeneratedReports as GeneratedReportsModel

    print(request.user)
    data = {
        "user": "Admin",
        "headers": [
            "Data Source",
            "Subscription",
            "Report Type",
            "Status",
            "Time Range",
            "Created At",
        ],
        "datas": [
            [
                gen.data_source,
                gen.subscription.display_name,
                gen.report_type,
                gen.status,
                f"{gen.time_range.lower.date()} - {gen.time_range.upper.date()}",
                gen.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            ]
            for gen in GeneratedReportsModel.objects.filter(deleted=False).order_by(
                "-created_at"
            )[:10]
        ],
        "lastAdded": MarketplacesModel.objects.order_by("-added").first(),
        "form": ReportForm(),
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
    try:
        sub = SubscriptionsModel.objects.get(subscription_id=subsId)
    except SubscriptionsModel.DoesNotExist:
        redirect("home")
        return None
    serveData = SubsData(sub=sub)
    data = {
        "subsName": sub.display_name,
        "pivotTable": {
            "Services": df_tohtml(serveData.service()),
            "Marketplaces": df_tohtml(serveData.marketplace()),
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
    print(request)
    return JsonResponse({"data": "ok", "req": request.POST})


def marketplace(request):
    subs = SubscriptionsModel.objects.all()
    for sub in subs:
        sub.objects.marketplace


@require_http_methods(["POST"])
def reports(request):
    from datetime import datetime

    from nilakandi.models import GeneratedReports as GeneratedReportsModel
    from nilakandi.models import GenerationStatusEnum
    from nilakandi.tasks import make_report

    decimal_count = request.POST.get("decimal_count", 8)
    start_date = datetime.strptime(request.POST.get("from_date"), "%Y-%m-%d").date()
    end_date = datetime.strptime(request.POST.get("to_date"), "%Y-%m-%d").date()
    subscription = SubscriptionsModel.objects.get(
        subscription_id=request.POST.get("subscription")
    )

    task = make_report.delay(
        report_type=request.POST.get("report_type"),
        decimal_count=int(decimal_count),
        start_date=start_date,
        end_date=end_date,
        subscription_id=subscription.subscription_id,
        source=request.POST.get("data_source", "db"),
    )
    gen_report = GeneratedReportsModel.objects.create(
        id=task.id,
        data_source=request.POST.get("data_source", "db"),
        subscription=subscription,
        report_type=request.POST.get("report_type"),
        report_data={},
        status=GenerationStatusEnum.IN_PROGRESS,
        time_range=(start_date, end_date),
    )
    gen_report.save()
    return redirect(
        "view_report",
        id=task.id,
    )


@require_http_methods(["POST"])
def get_report(request):
    import logging

    from django.core.cache import cache

    from nilakandi.models import GeneratedReports as GeneratedReportsModel
    from nilakandi.models import GenerationStatusEnum

    id = request.POST.get("id")
    if not id:
        return JsonResponse(
            data={"error": "Report ID is required."},
            status=400,
        )
    data = {
        "id": id,
        "status": GenerationStatusEnum.IN_PROGRESS.value,
        "page_title": None,
        "pivot": None,
    }
    report_cache = cache.get(id)
    if (
        isinstance(report_cache, dict)
        and report_cache.get("page_title", None) is not None
        and report_cache.get("pivot", None) is not None
    ):
        data["page_title"] = report_cache.get("page_title")
        data["pivot"] = report_cache.get("pivot")
        data["status"] = GenerationStatusEnum.COMPLETED.value
        return JsonResponse(data=data, status=200)
    elif (
        not isinstance(report_cache, dict)
        and GeneratedReportsModel.objects.filter(id=id).first().status
        == GenerationStatusEnum.COMPLETED.value
    ):
        report = GeneratedReportsModel.objects.filter(id=id).first().report_data
        cache.set(
            key=id,
            value={
                "page_title": report.get("page_title"),
                "pivot": report.get("pivot"),
            },
            timeout=60 * 60 * 24,
        )
        data["page_title"] = (report.get("page_title"),)
        data["pivot"] = report.get("pivot")
        data["status"] = GenerationStatusEnum.COMPLETED.value
        return JsonResponse(data=data, status=200)
    elif (
        GeneratedReportsModel.objects.filter(id=id).first().status
        == GenerationStatusEnum.IN_PROGRESS.value
    ):
        data["status"] = GenerationStatusEnum.IN_PROGRESS.value
        return JsonResponse(
            data=data,
            status=202,
        )
    elif (
        GeneratedReportsModel.objects.filter(id=id).first().status
        == GenerationStatusEnum.FAILED.value
    ):
        gen_report = GeneratedReportsModel.objects.filter(id=id).first()
        gen_report.deleted = True
        gen_report.save()
        # raise ValueError(
        #     f"Report generation failed for ID {id}. Please check the logs for more details."
        # )
        logging.getLogger("nilakandi.tasks").info("Report generation failed.")
        return JsonResponse(data=data, status=500)
    logging.getLogger("nilakandi.tasks").info("Report ID not found or invalid.")
    return JsonResponse(data=data, status=500)


def view_report(request, id):
    return render(request, "blank.html", context={"id": id})


def summary(request):
    from nilakandi.helper.report_generation import summary as summaryReport

    print(type(request))
    print(request)
    decimal_count = 0
    if request.method == "POST":
        decimal_count = int(request.POST.get("decimal_count", 8))
    data = {
        "pivot": df_tohtml(
            df=summaryReport(), decimal=decimal_count if decimal_count else 16
        ),
    }
    return render(request, "blank.html", context=data)


def services_report(request):
    from nilakandi.helper.report_generation import services as servicesReport

    data = {
        "pivot": df_tohtml(servicesReport()),
    }
    return render(request, "blank.html", context=data)


def marketplaces_report(request):
    from nilakandi.helper.report_generation import marketplaces as marketplacesReport

    data = {
        "pivot": df_tohtml(marketplacesReport()),
    }
    return render(request, "blank.html", context=data)


def virtualmachines_report(request):
    from nilakandi.helper.report_generation import (
        virtual_machine as virtualmachinesReport,
    )

    data = {
        "pivot": df_tohtml(virtualmachinesReport()),
    }
    return render(request, "blank.html", context=data)


def testForms(request):
    from nilakandi.forms import ReportForm

    form = ReportForm()
    data = {
        "form": form,
    }
    return render(request, "testform.html", context=data)
