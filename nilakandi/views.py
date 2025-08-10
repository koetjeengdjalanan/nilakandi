"""Nilakandi Views Module."""

from django.conf import settings
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from nilakandi.models import Marketplace as MarketplacesModel
from nilakandi.models import Services as ServicesModel
from nilakandi.models import Subscription as SubscriptionsModel

from .helper.azure_api import Auth, Services, Subscriptions
from .helper.miscellaneous import df_tohtml
from .helper.serve_data import SubsData


def home(request):
    """Render dashboard home page with recent generated reports and report form.

    Parameters
    ----------
    request : HttpRequest
        Incoming HTTP request.

    Returns:
    -------
    HttpResponse
        Rendered home.html template.
    """
    from nilakandi.forms import ReportForm
    from nilakandi.models import GeneratedReports as GeneratedReportsModel

    deleted: bool = request.GET.get("deleted", "false").lower() == "true"
    gen_reports = GeneratedReportsModel.objects.order_by("-created_at")
    if not deleted:
        gen_reports = gen_reports.filter(deleted=False)
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
            {
                "url": f"reports/{gen.id}",
                "data_source": gen.data_source,
                "subscription": gen.subscription.display_name,
                "report_type": gen.report_type,
                "status": gen.status,
                "time_range": (
                    f"{gen.time_range.lower.date()} - {gen.time_range.upper.date()}" if gen.time_range else "N/A"
                ),
                "created_at": gen.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for gen in gen_reports[:10]
        ],
        "lastAdded": MarketplacesModel.objects.order_by("-added").first(),
        "form": ReportForm(),
    }
    return render(request=request, template_name="home.html", context=data)


def subscriptions(request):
    """List all subscriptions.

    Parameters
    ----------
    request : HttpRequest

    Returns:
    -------
    HttpResponse
        Rendered subscriptions.html displaying subscriptions table.
    """
    subs = SubscriptionsModel.objects.all()
    data = {
        "subs": subs,
        "field_names": [field.name for field in SubscriptionsModel._meta.fields],
    }
    print(request)
    return render(request, "subscriptions.html", context=data)


def subscription_details(request, subsId):
    """Show detailed pivot reports for a specific subscription.

    Parameters
    ----------
    request : HttpRequest
    subsId : str
        Subscription ID (subscription_id field).

    Returns:
    -------
    HttpResponse | None
        Rendered subsreport.html or None if subscription not found (redirect initiated).
    """
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
    """Paginated listing of services cost records.

    Parameters
    ----------
    request : HttpRequest

    Query Params
    ------------
    perPage : int, optional
        Items per page (default 10).
    page : int, optional
        Page number.

    Returns:
    -------
    HttpResponse
        Rendered servicesCost.html.
    """
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
    """Fetch subscriptions from Azure and persist them.

    Parameters
    ----------
    request : HttpRequest

    Returns:
    -------
    JsonResponse
        JSON containing fetched subscription data.
    """
    auth = Auth(
        client_id=settings.AZURE_CLIENT_ID,
        client_secret=settings.AZURE_CLIENT_SECRET,
        tenant_id=settings.AZURE_TENANT_ID,
    )
    subs = Subscriptions(auth=auth).get()
    subs.db_save()
    return JsonResponse({"data": subs.res})


def testAPI(request):
    """Simple test endpoint that echoes POST payload structure.

    Parameters
    ----------
    request : HttpRequest

    Returns:
    -------
    JsonResponse
        Echo data.
    """
    print(request.POST)
    print(type(request.POST.getlist("file_list", [])))
    return JsonResponse({"data": "ok", "req": request.POST})


def marketplace(request):
    """Placeholder marketplace view (currently incomplete).

    Iterates subscriptions to trigger marketplace related lazy operations (no response).

    Parameters
    ----------
    request : HttpRequest

    Returns:
    -------
    None
        No HTTP response currently (likely bug / TODO).
    """
    subs = SubscriptionsModel.objects.all()
    for sub in subs:
        sub.objects.marketplace


def historical_report(request):
    """Paginated and searchable list of historical generated reports (partial view).

    Parameters
    ----------
    request : HttpRequest

    Query Params
    ------------
    include_deleted : bool
        Include soft-deleted reports if true.
    keyword : str
        Optional search keyword.
    page : int
        Page number.

    Returns:
    -------
    HttpResponse
        Rendered partial/historical_report.html.
    """
    from django.core.paginator import Paginator

    from nilakandi.models import GeneratedReports as GeneratedReportsModel

    gen_reports = GeneratedReportsModel.objects.order_by("-created_at")
    deleted = request.GET.get("include_deleted", "false").lower() == "true"
    gen_reports = gen_reports.filter(deleted=False) if not deleted else gen_reports
    if request.GET.get("keyword", None) is not None and request.GET.get("keyword", "").strip() != "":
        from django.contrib.postgres.search import SearchVector

        keyword = request.GET.get("keyword", "").strip()
        gen_reports = gen_reports.annotate(
            search=SearchVector(
                "data_source",
                "subscription__display_name",
                "report_type",
                "time_range",
                "created_at",
            )
        ).filter(search=keyword)
    paginator = Paginator(gen_reports, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    current_page = page_obj.number if page_obj else 1
    start_page = max(current_page - 5, 1)
    end_page = min(current_page + 5, paginator.num_pages)
    limited_pages_range = range(start_page, end_page + 1)
    data = {
        "page_obj": page_obj,
        "page_range": limited_pages_range,
        "max_pages": paginator.num_pages,
        "deleted": deleted,
        "headers": [
            "Data Source",
            "Subscription",
            "Report Type",
            "Status",
            "Time Range",
            "Created At",
        ],
        "datas": [
            {
                "url": f"reports/{gen.id}",
                "data_source": gen.data_source,
                "subscription": gen.subscription.display_name,
                "report_type": gen.report_type,
                "status": gen.status,
                "time_range": (
                    f"{gen.time_range.lower.date()} - {gen.time_range.upper.date()}" if gen.time_range else "N/A"
                ),
                "created_at": gen.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for gen in page_obj.object_list
        ],
    }
    return render(request, "partial/historical_report.html", context=data)


def view_report(request, id):
    """Render a simple placeholder page for a specific report.

    Parameters
    ----------
    request : HttpRequest
    id : int | str
        Generated report identifier.

    Returns:
    -------
    HttpResponse
        Rendered blank.html.
    """
    return render(request, "blank.html", context={"id": id})


def summary(request):
    """Generate and render summary pivot report.

    Parameters
    ----------
    request : HttpRequest

    POST Params
    -----------
    decimal_count : int
        Optional decimal precision for numeric formatting.

    Returns:
    -------
    HttpResponse
        Rendered blank.html with pivot HTML.
    """
    from nilakandi.helper.report_generation import summary as summaryReport

    print(type(request))
    print(request)
    decimal_count = 0
    if request.method == "POST":
        decimal_count = int(request.POST.get("decimal_count", 8))
    data = {
        "pivot": df_tohtml(df=summaryReport(), decimal=decimal_count if decimal_count else 16),
    }
    return render(request, "blank.html", context=data)


def services_report(request):
    """Generate services cost pivot report.

    Parameters
    ----------
    request : HttpRequest

    Returns:
    -------
    HttpResponse
        Rendered blank.html with services pivot.
    """
    from nilakandi.helper.report_generation import services as servicesReport

    data = {
        "pivot": df_tohtml(servicesReport()),
    }
    return render(request, "blank.html", context=data)


def marketplaces_report(request):
    """Generate marketplaces cost pivot report.

    Parameters
    ----------
    request : HttpRequest

    Returns:
    -------
    HttpResponse
        Rendered blank.html with marketplaces pivot.
    """
    from nilakandi.helper.report_generation import marketplaces as marketplacesReport

    data = {
        "pivot": df_tohtml(marketplacesReport()),
    }
    return render(request, "blank.html", context=data)


def virtualmachines_report(request):
    """Generate virtual machines cost pivot report.

    Parameters
    ----------
    request : HttpRequest

    Returns:
    -------
    HttpResponse
        Rendered blank.html with virtual machines pivot.
    """
    from nilakandi.helper.report_generation import virtual_machine as virtualmachinesReport

    data = {
        "pivot": df_tohtml(virtualmachinesReport()),
    }
    return render(request, "blank.html", context=data)


def testForms(request):
    """Render a test page showing the report form.

    Parameters
    ----------
    request : HttpRequest

    Returns:
    -------
    HttpResponse
        Rendered testform.html containing the form.
    """
    from nilakandi.forms import ReportForm

    form = ReportForm()
    data = {
        "form": form,
    }
    return render(request, "testform.html", context=data)


def list_blobs_from_azure(request):
    """List CSV blobs per container from Azure Blob Storage.

    Parameters
    ----------
    request : HttpRequest

    Returns:
    -------
    HttpResponse | None
        Rendered partial/blob_list.html with blob metadata or None if no blobs.
    """
    from nilakandi.helper.azure_api import Auth
    from nilakandi.helper.azure_blob import Blobs

    auth = Auth(
        client_id=settings.AZURE_CLIENT_ID,
        client_secret=settings.AZURE_CLIENT_SECRET,
        tenant_id=settings.AZURE_TENANT_ID,
    )
    blobs = Blobs(
        container_name="testcontainer",
        auth=auth,
        subscription=SubscriptionsModel.objects.first(),
    )
    containers = blobs.blob_service_client.list_containers(include_metadata=True)
    blob_list: list[dict[str, str | list]] = []
    for container in containers:
        try:
            container_name = container.get("name")
            files = blobs.blob_service_client.get_container_client(container=container_name).list_blobs()
            blob_list.append(
                {
                    "container": container_name,
                    "files": [doc.get("name") for doc in files if doc.get("name").endswith(".csv")],
                }
            )
            subscriptions = SubscriptionsModel.objects.values_list("display_name", flat=True)
        except Exception as e:
            print(e)
        finally:
            continue
    if len(blob_list) == 0:
        return None
    return render(
        request,
        "partial/blob_list.html",
        context={"blobs": blob_list, "subscriptions": subscriptions},
    )


def operation_details_or_list(request, ops_id=None):
    """Operation Viewer.

    Display details for a specific operation if ops_id is provided (context key: 'operation'),
    otherwise list all operations with pagination (context key: 'operations').

    Parameters
    ----------
    request : HttpRequest
        The HTTP request object.
    ops_id : str or None
        The UUID of the operation to display details for, or None to list all operations.

    Returns:
        HttpResponse: Rendered HTML page with operation details or a paginated list of operations.
    """
    from uuid import UUID

    from django.core.paginator import Paginator

    from nilakandi.models import Operation as OperationsModel

    if ops_id:
        raise NotImplementedError("Operation details view is not implemented yet.")
        operation = get_object_or_404(OperationsModel, id=UUID(ops_id))
        return render(request, "partial/operation_details.html", context={"operation": operation})

    operations = OperationsModel.objects.order_by("-started")
    paginator = Paginator(object_list=operations, per_page=10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    context = {
        "operations": page_obj.object_list,
        "page_obj": page_obj,
    }
    return render(request, "operations.html", context=context)
