from django.contrib import admin
from django.utils.html import format_html

from .models import MonitoredProcess, ProcessTag


@admin.register(MonitoredProcess)
class MonitoredProcessAdmin(admin.ModelAdmin):
    list_display = [
        'label', 'status_badge', 'source_short',
        'last_checked_at', 'last_changed_at', 'created_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['label', 'source', 'resolved_url', 'notes']
    readonly_fields = [
        'created_at', 'updated_at', 'last_hash',
        'last_checked_at', 'last_changed_at', 'last_error',
    ]
    fieldsets = (
        ('Identificação', {
            'fields': ('label', 'source', 'resolved_url', 'status'),
        }),
        ('Configuração', {
            'fields': ('check_interval_seconds', 'notes'),
        }),
        ('Estado interno (somente leitura)', {
            'classes': ('collapse',),
            'fields': (
                'last_hash', 'last_checked_at', 'last_changed_at',
                'last_error', 'created_at', 'updated_at',
            ),
        }),
    )
    ordering = ['-last_changed_at', '-updated_at']

    @admin.display(description='Status')
    def status_badge(self, obj):
        colors = {
            'active': '#15803d',
            'paused': '#b45309',
            'error': '#dc2626',
            'archived': '#6b7280',
        }
        color = colors.get(obj.status, '#374151')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700">{}</span>',
            color, obj.get_status_display(),
        )

    @admin.display(description='Fonte')
    def source_short(self, obj):
        s = obj.source
        return s[:60] + '...' if len(s) > 60 else s


@admin.register(ProcessTag)
class ProcessTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'process']
    list_filter = ['process']
    search_fields = ['name', 'process__label']
