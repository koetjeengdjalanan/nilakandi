"""Collection of Nilakandi URLS."""

from django.urls import include, path

from . import apis, views

urlpatterns = [
    path("", views.home, name="home"),
    path("subscription/", views.subscriptions, name="subscriptions"),
    path(
        "subscription/<uuid:subsId>/",
        views.subscription_details,
        name="subscription details",
    ),
    path("services/", views.services, name="services"),
    path("testAPI/", views.testAPI, name="testAPI"),
    path("blob_list/", views.list_blobs_from_azure, name="blob_list"),
    path(
        "reports/",
        include(
            [
                path("", views.historical_report, name="report_lists"),
                path("<uuid:id>/", views.view_report, name="view_report"),
                path("summary/", views.summary, name="summary"),
                path("services/", views.services_report, name="services report"),
                path(
                    "marketplaces/",
                    views.marketplaces_report,
                    name="marketplaces report",
                ),
                path(
                    "virtualmachines/",
                    views.virtualmachines_report,
                    name="virtualmachines report",
                ),
            ]
        ),
    ),
    path("operations/", views.operation_details_or_list, name="operations"),
    path("operations/<uuid:ops_id>/", views.operation_details_or_list, name="operations_details"),
    path(
        "api/",
        include(
            [
                path("reports/", apis.reports, name="api_reports"),
                path("get_report/", apis.get_report, name="get_report"),
                path("upload_report/", apis.upload_report, name="upload_report"),
            ]
        ),
    ),
]
