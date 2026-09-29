"""Queries reutilizáveis do app precedentes. Lógica de negócio fica em services.py."""
from __future__ import annotations

from django.db.models import Q, QuerySet

from .models import PrecedentAnalysis, PrecedentEntity, PrecedentFact


def current_facts(entity: PrecedentEntity) -> QuerySet[PrecedentFact]:
    return PrecedentFact.objects.filter(entity=entity, is_current=True)


def fact_history(fact: PrecedentFact) -> QuerySet[PrecedentFact]:
    raiz_id = fact.root_id or fact.pk
    return PrecedentFact.objects.filter(Q(pk=raiz_id) | Q(root_id=raiz_id)).order_by('created_at')


def case_analyses(case) -> QuerySet[PrecedentAnalysis]:
    return case.analyses.all().prefetch_related('facts')
