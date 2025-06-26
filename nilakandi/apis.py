from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods


@require_http_methods(["POST"])
def reports(request: HttpRequest):
    from datetime import datetime

    from nilakandi.models import GeneratedReports as GeneratedReportsModel
    from nilakandi.models import GenerationStatusEnum
    from nilakandi.models import Subscription as SubscriptionsModel
    from nilakandi.tasks import make_report

    request_date = (
        request.POST.get("from_date", None),
        request.POST.get("to_date", None),
    )
    decimal_count = request.POST.get("decimal_count", 8)
    start_date = (
        datetime.now()
        if request_date[0] is None
        else datetime.strptime(request_date[0], "%Y-%m-%d").date()
    )
    end_date = (
        datetime.now()
        if request_date[1] is None
        else datetime.strptime(request_date[1], "%Y-%m-%d").date()
    )
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
        file_list=request.POST.getlist("file_list", []),
    )
    gen_report = GeneratedReportsModel.objects.create(
        id=task.id,
        data_source=request.POST.get("data_source", "db"),
        subscription=subscription,
        report_type=request.POST.get("report_type"),
        report_data={},
        status=GenerationStatusEnum.IN_PROGRESS.value,
        time_range=(start_date, end_date),
    )
    gen_report.save()
    return redirect(
        "view_report",
        id=task.id,
    )


@require_http_methods(["POST"])
def get_report(request: HttpRequest):
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
        logging.getLogger("nilakandi.tasks").info("Report generation failed.")
        return JsonResponse(data=data, status=500)
    logging.getLogger("nilakandi.tasks").info("Report ID not found or invalid.")
    return JsonResponse(data=data, status=500)


@require_http_methods(["POST"])
def upload_report(request: HttpRequest):
    import logging
    import tempfile

    logger = logging.getLogger("nilakandi.pull")

    try:
        report_type = request.POST.get("report_type")
        if not report_type:
            return JsonResponse(
                data={"message": "The 'report_type' is required."}, status=400
            )

        uploaded_files = request.FILES.values()
        if not uploaded_files:
            return JsonResponse(data={"message": "No files were uploaded."}, status=400)

        # Check file sizes (warn if > 100MB)
        total_size = sum(file.size for file in uploaded_files)
        logger.info(
            f"Processing {len(uploaded_files)} files, total size: {total_size / (1024*1024):.2f}MB"
        )

        if total_size > 536870912:  # 512MB
            return JsonResponse(
                data={"message": "Total file size exceeds 512MB limit."}, status=413
            )

        paths = []
        for file in uploaded_files:
            file_name = file.name.replace(" ", "_")
            logger.info(
                f"Processing file: {file_name} ({file.size / (1024*1024):.2f}MB)"
            )

            with tempfile.NamedTemporaryFile(
                delete=False, prefix="nilakandi_raw-", suffix=f"_{file_name}"
            ) as temp_file:
                for chunk in file.chunks():
                    temp_file.write(chunk)
                paths.append(temp_file.name)

        data = request
        data.POST = request.POST.copy()
        data.POST["report_type"] = report_type
        data.POST["decimal_count"] = request.POST.get("decimal_count", 8)
        data.POST["data_source"] = "byof"
        data.POST["file_list"] = paths

        response = reports(request=data)

        if hasattr(response, "url"):
            return JsonResponse({"redirect_url": response.url})

        return response

    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        return JsonResponse(data={"message": f"Upload failed: {str(e)}"}, status=500)
