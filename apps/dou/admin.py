from django.contrib import admin

from .models import DouAnticipation, DouFetchState, DouMonitoredTerm, DouSendLog, DouSubscription


class DouMonitoredTermInline(admin.TabularInline):
    model = DouMonitoredTerm
    extra = 1


@admin.register(DouSubscription)
class DouSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('subscriber', 'enabled', 'nextday_enabled', 'nextday_time')
    list_filter = ('enabled', 'nextday_enabled')
    search_fields = ('subscriber__name', 'subscriber__email')
    inlines = [DouMonitoredTermInline]


@admin.register(DouSendLog)
class DouSendLogAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'kind', 'reference_date', 'status', 'sent_at')
    list_filter = ('kind', 'status')
    date_hierarchy = 'sent_at'


@admin.register(DouFetchState)
class DouFetchStateAdmin(admin.ModelAdmin):
    list_display = ('source', 'last_attempt_at', 'last_success_at')


@admin.register(DouAnticipation)
class DouAnticipationAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'reference_date', 'updated_at')
    date_hierarchy = 'reference_date'
