from django.contrib import admin

from .models import AppSetting, CheckRun, DetectedChange, PageSnapshot


@admin.register(CheckRun)
class CheckRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'process', 'status', 'started_at', 'finished_at', 'error_short']
    list_filter = ['status', 'started_at']
    search_fields = ['process__label', 'error_message']
    readonly_fields = ['started_at', 'finished_at']
    ordering = ['-started_at']

    @admin.display(description='Erro')
    def error_short(self, obj):
        if not obj.error_message:
            return '—'
        return obj.error_message[:80] + '…' if len(obj.error_message) > 80 else obj.error_message


@admin.register(PageSnapshot)
class PageSnapshotAdmin(admin.ModelAdmin):
    list_display = ['id', 'process', 'content_hash_short', 'fetched_at']
    list_filter = ['fetched_at', 'process']
    search_fields = ['process__label', 'content_hash']
    readonly_fields = ['fetched_at', 'content_hash']
    ordering = ['-fetched_at']

    @admin.display(description='Hash')
    def content_hash_short(self, obj):
        return obj.content_hash[:16] + '…'


@admin.register(DetectedChange)
class DetectedChangeAdmin(admin.ModelAdmin):
    list_display = ['id', 'process', 'summary_short', 'review', 'detected_at']
    list_filter = ['review', 'detected_at', 'process']
    search_fields = ['process__label', 'summary', 'diff_text']
    readonly_fields = ['detected_at', 'old_hash', 'new_hash']
    ordering = ['-detected_at']

    @admin.display(description='Resumo')
    def summary_short(self, obj):
        return obj.summary[:100] + '…' if len(obj.summary) > 100 else obj.summary


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ['key', 'value_short', 'updated_at']
    search_fields = ['key']
    readonly_fields = ['updated_at']

    @admin.display(description='Valor')
    def value_short(self, obj):
        return obj.value[:80] + '…' if len(obj.value) > 80 else obj.value
