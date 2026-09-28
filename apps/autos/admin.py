from django.contrib import admin

from .models import AutosPackageJob


@admin.register(AutosPackageJob)
class AutosPackageJobAdmin(admin.ModelAdmin):
    list_display = ('process', 'status', 'total_declared', 'total_processed', 'created_at', 'expires_at')
    list_filter = ('status',)
    search_fields = ('process__label',)
