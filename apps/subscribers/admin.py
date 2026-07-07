from django.contrib import admin

from .models import ProcessSubscription, Subscriber


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'email', 'phone',
        'email_enabled', 'whatsapp_enabled', 'silent_mode', 'paused_until',
    ]
    list_filter = ['email_enabled', 'whatsapp_enabled', 'silent_mode']
    search_fields = ['name', 'email', 'phone']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ProcessSubscription)
class ProcessSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['subscriber', 'process', 'email_enabled', 'whatsapp_enabled', 'created_at']
    list_filter = ['email_enabled', 'whatsapp_enabled']
    search_fields = ['subscriber__name', 'process__label']
    autocomplete_fields = ['subscriber', 'process']
    readonly_fields = ['created_at']
