from django.urls import include, path

from . import views

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
    path(
        "reports/",
        include(
            [
                path("", views.reports, name="reports"),
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
]
