from django.contrib import admin

from .models import Notification, NotificationAttempt


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'channel', 'destination_short', 'status',
        'attempts', 'sent_at', 'created_at',
    ]
    list_filter = ['channel', 'status', 'created_at']
    search_fields = ['destination', 'change__process__label', 'error_message']
    readonly_fields = ['created_at', 'sent_at']
    ordering = ['-created_at']

    @admin.display(description='Destino')
    def destination_short(self, obj):
        d = obj.destination
        return d[:40] + '…' if len(d) > 40 else d


@admin.register(NotificationAttempt)
class NotificationAttemptAdmin(admin.ModelAdmin):
    list_display = ['id', 'notification', 'status', 'error_short', 'attempted_at']
    list_filter = ['status', 'attempted_at']
    ordering = ['-attempted_at']

    @admin.display(description='Erro')
    def error_short(self, obj):
        if not obj.error:
            return '—'
        return obj.error[:60] + '…' if len(obj.error) > 60 else obj.error
