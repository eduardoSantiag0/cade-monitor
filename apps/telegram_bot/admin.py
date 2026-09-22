from django.contrib import admin

from apps.subscribers.models import ProcessSubscription

from .models import BotAction, TelegramChat, TelegramUpdate


class ChatSubscriptionInline(admin.TabularInline):
    model = ProcessSubscription
    fk_name = 'subscriber'
    fields = ['process', 'telegram_enabled', 'paused', 'created_at']
    readonly_fields = ['process', 'created_at']
    extra = 0
    can_delete = False


@admin.register(TelegramChat)
class TelegramChatAdmin(admin.ModelAdmin):
    list_display = ['title', 'chat_type', 'username', 'is_reachable', 'subscription_count', 'last_seen_at']
    list_filter = ['chat_type', 'is_reachable']
    search_fields = ['title', 'username', 'chat_id']
    readonly_fields = ['chat_id', 'chat_type', 'subscriber', 'created_at', 'updated_at', 'last_seen_at']

    @admin.display(description='processos')
    def subscription_count(self, obj):
        return obj.subscriber.subscriptions.count()


@admin.register(BotAction)
class BotActionAdmin(admin.ModelAdmin):
    list_display = ['kind', 'process', 'chat', 'status', 'attempts', 'next_attempt_at', 'requested_at']
    list_filter = ['kind', 'status']
    search_fields = ['process__label', 'process__source', 'chat__title']
    readonly_fields = ['requested_at', 'finished_at']


@admin.register(TelegramUpdate)
class TelegramUpdateAdmin(admin.ModelAdmin):
    list_display = ['update_id', 'received_at']
    readonly_fields = ['update_id', 'received_at']
