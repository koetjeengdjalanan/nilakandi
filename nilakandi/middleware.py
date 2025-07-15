from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.urls import reverse


class ForceTemporaryFileUploadHandlerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # We only want to apply this middleware to the specific upload view
        try:
            upload_url = reverse("upload_report")
            if request.path == upload_url:
                request.upload_handlers = [TemporaryFileUploadHandler(request=request)]
        except Exception:
            # Fails gracefully if the URL is not found, during tests for example
            pass

        response = self.get_response(request)
        return response
