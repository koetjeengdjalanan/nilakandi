"""This module contains API endpoints for generating and retrieving reports."""

from datetime import datetime

from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods


# TODO: Implement multiple report generation operation tracking using `nilakandi.models.Operation`
@require_http_methods(["POST"])
def reports(request: HttpRequest):
    """Process a request to generate a report as a background task.

    This view function handles POST requests to create reports. It extracts
    parameters from the request, validates and formats them as needed, then
    launches a background task to generate the report. After starting the task,
    it redirects the user to a page where they can view the report's progress
    or results.

    Args:
        request (HttpRequest): The HTTP request object containing POST data with report parameters.
                            Expected POST parameters include:
                            - from_date (str, optional): Start date in 'YYYY-MM-DD' format
                            - to_date (str, optional): End date in 'YYYY-MM-DD' format
                            - decimal_count (int, optional): Precision for decimal numbers, defaults to 8
                            - subscription (str, optional): Subscription ID or 'all'
                            - report_type (str, optional): Type of report to generate, defaults to 'all'
                            - data_source (str, optional): Source of data, defaults to 'db'
                            - file_list (list, optional): List of files to include in the report

    Returns:
        HttpResponseRedirect: Redirects to 'view_report' with the task ID

    Notes:
        The file_list parameter can be a JSON-encoded list of strings or regular strings.
        If dates are not provided, the current date is used.
    """
    from json import JSONDecodeError, loads

    from nilakandi.tasks import make_report

    def check_files(item: str) -> list[str] | str:
        if item is None or item.strip() == "":
            return item
        try:
            parsed = loads(item)
            if isinstance(parsed, list) and all(isinstance(i, str) for i in parsed):
                return parsed
            else:
                return item
        except (JSONDecodeError, TypeError) as error:
            print(f"Error parsing item {item}: {error}")
            return item

    request_date = (
        request.POST.get("from_date", None),
        request.POST.get("to_date", None),
    )
    decimal_count = request.POST.get("decimal_count", 8)
    start_date = datetime.now() if request_date[0] is None else datetime.strptime(request_date[0], "%Y-%m-%d").date()
    end_date = datetime.now() if request_date[1] is None else datetime.strptime(request_date[1], "%Y-%m-%d").date()
    subscription = request.POST.get("subscription", "all")

    if request.POST.getlist("file_list", None) is not None:
        file_list = [check_files(item) for item in request.POST.getlist("file_list", None)]
    else:
        file_list = None

    make_report.delay(
        report_type=request.POST.get("report_type", "all"),
        decimal_count=int(decimal_count),
        start_date=start_date,
        end_date=end_date,
        subscription_id=subscription,
        source=request.POST.get("data_source", "db"),
        file_list=file_list,
    )
    return redirect("operations")


@require_http_methods(["POST"])
def get_report(request: HttpRequest):
    """Retrieves a generated report based on the provided ID.

    This endpoint checks for the report in cache first, then falls back to the database.
    The response status and content depend on the report's generation status.

    Args:
        request (HttpRequest): The HTTP request object containing POST data.
                              Must include an 'id' parameter.

    Returns:
        JsonResponse: A response with the following structure:
            {
                "id": str,                # The report ID
                "status": str,            # The report generation status
                "page_title": str|None,   # The report's page title if completed
                "pivot": dict|None        # The report's pivot data if completed

        HTTP Status codes:
            200: Report retrieved successfully
            202: Report generation is in progress
            400: Missing report ID
            500: Report generation failed or report not found

    Cache behavior:
        - If the report is found in cache with complete data, it's returned immediately
        - If the report is found in the database but not in cache, it's cached for 24 hours

    Side effects:
        - Failed reports are marked as deleted in the database
    """
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
        and GeneratedReportsModel.objects.filter(id=id).first().status == GenerationStatusEnum.COMPLETED.value
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
    elif GeneratedReportsModel.objects.filter(id=id).first().status == GenerationStatusEnum.IN_PROGRESS.value:
        data["status"] = GenerationStatusEnum.IN_PROGRESS.value
        return JsonResponse(
            data=data,
            status=202,
        )
    elif GeneratedReportsModel.objects.filter(id=id).first().status == GenerationStatusEnum.FAILED.value:
        gen_report = GeneratedReportsModel.objects.filter(id=id).first()
        gen_report.deleted = True
        gen_report.save()
        logging.getLogger("nilakandi.tasks").info("Report generation failed.")
        return JsonResponse(data=data, status=500)
    logging.getLogger("nilakandi.tasks").info("Report ID not found or invalid.")
    return JsonResponse(data=data, status=500)


@require_http_methods(["POST"])
def upload_report(request: HttpRequest):
    """Process uploaded report files from an HTTP request.

    This function handles file uploads for reports, validates input parameters,
    manages file size limits, and processes the files by saving them as temporary
    files on disk to avoid memory issues.

    Args:
        request (HttpRequest): The Django HTTP request object containing uploaded
                              files and form data.

    Returns:
        JsonResponse or HttpResponse:
            - JsonResponse with error message and appropriate status code if validation fails
            - JsonResponse with redirect_url if processing succeeds and results in a redirect
            - Response from the reports() function otherwise

    Raises:
        Exception: Any exceptions during processing are caught, logged, and returned
                   as a 500 status JsonResponse.

    Notes:
        - Requires 'report_type' in request.POST
        - Handles files efficiently to minimize memory usage
        - Enforces a 512MB total file size limit
        - Temporary files are created with 'nilakandi_raw-' prefix
    """
    import logging
    import os
    import tempfile

    logger = logging.getLogger("nilakandi.pull")
    paths = []

    try:
        report_type = request.POST.get("report_type")
        if not report_type:
            return JsonResponse(data={"message": "The 'report_type' is required."}, status=400)

        uploaded_files = list(request.FILES.values())
        if not uploaded_files:
            return JsonResponse(data={"message": "No files were uploaded."}, status=400)

        # Check file sizes
        total_size = sum(file.size for file in uploaded_files)
        logger.info(f"Receiving {len(uploaded_files)} files, total size: {total_size / (1024*1024):.2f}MB")

        if total_size > 536870912:  # 512MB
            return JsonResponse(data={"message": "Total file size exceeds 512MB limit."}, status=413)

        for file in uploaded_files:
            file_name = file.name.replace(" ", "_")
            logger.info(f"Received file: {file_name} ({file.size / (1024*1024):.2f}MB)")

            # Instead of reading the file into memory, just use the path Django created
            if hasattr(file, "temporary_file_path"):
                temp_path = file.temporary_file_path()
                # Create a new permanent temporary file to avoid cleanup by Django
                with tempfile.NamedTemporaryFile(
                    delete=False, prefix="nilakandi_raw-", suffix=f"_{file_name}"
                ) as new_temp_file:
                    # Copy file using operating system commands to avoid memory issues
                    os.system(f"cp '{temp_path}' '{new_temp_file.name}'")
                    paths.append(new_temp_file.name)
            else:
                # Fallback if file wasn't stored on disk
                with tempfile.NamedTemporaryFile(
                    delete=False, prefix="nilakandi_raw-", suffix=f"_{file_name}"
                ) as temp_file:
                    # Read and write in chunks to minimize memory usage
                    for chunk in file.chunks(chunk_size=1024 * 1024):  # 1MB chunks
                        temp_file.write(chunk)
                    paths.append(temp_file.name)

        data = request
        data.POST = request.POST.copy()
        data.POST["report_type"] = report_type
        data.POST["decimal_count"] = request.POST.get("decimal_count", 8)
        data.POST["data_source"] = "byof"
        data.POST.setlist("file_list", paths)

        response = reports(request=data)

        if hasattr(response, "url"):
            return JsonResponse({"redirect_url": response.url})

        return response

    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        return JsonResponse(data={"message": f"Upload failed: {str(e)}"}, status=500)
