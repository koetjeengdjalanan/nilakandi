from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("subscription/", views.subscriptions, name="subscriptions"),
    path(
        "subscription/detail/<uuid:subsId>/",
        views.subscriptions_detail,
        name="htmx_subscription_detail",
    ),
    path(
        "subscription/<uuid:subsId>/",
        views.subscription_details,
        name="subscription details",
    ),
    path("services/", views.services, name="services"),
    path("testAPI/", views.testAPI, name="testAPI"),
    path("htmxTest/", views.htmx_example, name="htmxExample"),
    path("htmxList/", views.htmx_list, name="htmxList"),
    # HTMX Modal paths
    path("htmxTest/create/modal/", views.htmx_create_modal, name="htmx_create_modal"),
    path(
        "htmxTest/update/<uuid:pk>/modal/",
        views.htmx_update_modal,
        name="htmx_update_modal",
    ),
    path("htmxTest/create/", views.htmx_test_create, name="htmx_create"),
    path("htmxTest/update/<uuid:pk>/", views.htmx_test_update, name="htmx_update"),
    path("htmxTest/delete/<uuid:pk>/", views.htmx_test_delete, name="htmx_delete"),
]
