from django.contrib import admin

from .models import Marketplace, Operation, Services, Subscription

admin.site.register(Services)
admin.site.register(Subscription)
admin.site.register(Operation)
admin.site.register(Marketplace)
