from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("subscription/<uuid:subsId>/", views.subscription, name="subscription"),
    path("services/", views.services, name="services"),
    path("testAPI/", views.testAPI, name="testAPI"),
]
