from django.contrib import admin

from .models import CadeCalendarEntry, CadeCalendarYear, ProcessInvite


class CadeCalendarEntryInline(admin.TabularInline):
    model = CadeCalendarEntry
    extra = 0


@admin.register(CadeCalendarYear)
class CadeCalendarYearAdmin(admin.ModelAdmin):
    list_display = ('year', 'status', 'official_act', 'last_checked_at', 'next_check_at')
    list_filter = ('status',)
    inlines = [CadeCalendarEntryInline]


@admin.register(ProcessInvite)
class ProcessInviteAdmin(admin.ModelAdmin):
    list_display = ('process', 'deadline_type', 'event_date', 'sequence', 'status', 'is_estimate')
    list_filter = ('deadline_type', 'status')
    search_fields = ('process__label',)
