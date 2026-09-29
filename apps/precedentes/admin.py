from django.contrib import admin

from .models import PrecedentAnalysis, PrecedentCase, PrecedentEntity, PrecedentFact


class PrecedentEntityInline(admin.TabularInline):
    model = PrecedentEntity
    extra = 0


@admin.register(PrecedentCase)
class PrecedentCaseAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'cliente', 'created_by', 'created_at')
    search_fields = ('titulo', 'cliente')
    inlines = [PrecedentEntityInline]


@admin.register(PrecedentEntity)
class PrecedentEntityAdmin(admin.ModelAdmin):
    list_display = ('razao_social', 'case', 'papel', 'cnpj')
    list_filter = ('papel',)
    search_fields = ('razao_social', 'cnpj')


@admin.register(PrecedentFact)
class PrecedentFactAdmin(admin.ModelAdmin):
    list_display = ('campo', 'valor', 'entity', 'status', 'is_current', 'created_at')
    list_filter = ('status', 'is_current')
    search_fields = ('campo', 'valor')


@admin.register(PrecedentAnalysis)
class PrecedentAnalysisAdmin(admin.ModelAdmin):
    list_display = ('case', 'texto', 'created_by', 'created_at')
