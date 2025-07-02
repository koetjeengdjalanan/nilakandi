from django.contrib import admin

from nilakandi.models import (
    ExportHistory,
    ExportReport,
    Marketplace,
    Operation,
    Services,
    Subscription,
)

admin.site.register(Services)
admin.site.register(Subscription)
admin.site.register(Operation)
admin.site.register(Marketplace)
admin.site.register(ExportHistory)
admin.site.register(ExportReport)
