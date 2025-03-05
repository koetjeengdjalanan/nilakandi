from django.urls import path
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
]
