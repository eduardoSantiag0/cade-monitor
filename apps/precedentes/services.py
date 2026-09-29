"""
Regras de negócio do app precedentes (spec 013). Views só validam formulário e
chamam estas funções — nenhuma lógica de negócio em views/models/templates.
Ver specs/013-precedentes-due-diligence/contracts/precedentes.md.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .models import PrecedentAnalysis, PrecedentCase, PrecedentEntity, PrecedentFact


def create_case(user, titulo: str, cliente: str = '', notas: str = '') -> PrecedentCase:
    return PrecedentCase.objects.create(created_by=user, titulo=titulo, cliente=cliente, notas=notas)


def add_entity(case: PrecedentCase, papel: str, razao_social: str, cnpj: str = '', pais: str = 'Brasil') -> PrecedentEntity:
    return PrecedentEntity.objects.create(
        case=case, papel=papel, razao_social=razao_social, cnpj=cnpj, pais=pais or 'Brasil',
    )


def update_entity(entity: PrecedentEntity, **campos) -> PrecedentEntity:
    """FR-002: atualiza os dados da empresa existente, sem criar uma segunda linha."""
    for campo, valor in campos.items():
        setattr(entity, campo, valor)
    entity.save(update_fields=list(campos.keys()))
    return entity


def remove_entity(entity: PrecedentEntity) -> None:
    """FR-012: a cascata nativa do Django remove os PrecedentFact da empresa; em
    seguida, remove qualquer PrecedentAnalysis do mesmo caso que tenha ficado sem
    nenhum fato-base restante (todos eram só dessa empresa) — análises com fatos de
    outras empresas sobrevivem, só perdendo o link para os fatos removidos."""
    case = entity.case
    with transaction.atomic():
        entity.delete()
        for analysis in case.analyses.all():
            if not analysis.facts.exists():
                analysis.delete()


def _validate_fact_fields(status: str, fonte_descricao: str, fonte_url: str, valor: str) -> None:
    if not (valor or '').strip():
        raise ValidationError('Um fato precisa de um valor.')  # FR-005
    if status == PrecedentFact.Status.CONFIRMADO and not (fonte_descricao or fonte_url):
        # FR-004: "confirmado sem citação não é confirmado".
        raise ValidationError('Um fato "confirmado" precisa de uma fonte.')


def record_fact(
    entity: PrecedentEntity, user, campo: str, valor: str, status: str,
    fonte_descricao: str = '', fonte_url: str = '', citacao: str = '',
) -> PrecedentFact:
    _validate_fact_fields(status, fonte_descricao, fonte_url, valor)
    return PrecedentFact.objects.create(
        entity=entity, created_by=user, campo=campo, valor=valor, status=status,
        fonte_descricao=fonte_descricao, fonte_url=fonte_url, citacao=citacao,
    )


def correct_fact(fact: PrecedentFact, user, motivo: str, **campos_novos) -> PrecedentFact:
    """FR-006/FR-007: nunca sobrescreve — cria uma nova versão, desativa a atual.
    `motivo` é obrigatório. Resolve a raiz do grupo mesmo se `fact` já for uma
    correção (nunca cria uma segunda cadeia desconectada)."""
    if not (motivo or '').strip():
        raise ValidationError('Toda correção precisa de um motivo.')

    status = campos_novos.get('status', fact.status)
    valor = campos_novos.get('valor', fact.valor)
    fonte_descricao = campos_novos.get('fonte_descricao', fact.fonte_descricao)
    fonte_url = campos_novos.get('fonte_url', fact.fonte_url)
    _validate_fact_fields(status, fonte_descricao, fonte_url, valor)

    raiz_id = fact.root_id or fact.pk
    with transaction.atomic():
        PrecedentFact.objects.filter(Q(pk=raiz_id) | Q(root_id=raiz_id), is_current=True).update(
            is_current=False,
        )
        nova = PrecedentFact.objects.create(
            entity=fact.entity,
            root_id=raiz_id,
            is_current=True,
            created_by=user,
            campo=campos_novos.get('campo', fact.campo),
            valor=valor,
            status=status,
            fonte_descricao=fonte_descricao,
            fonte_url=fonte_url,
            citacao=campos_novos.get('citacao', fact.citacao),
            motivo=motivo,
        )
    return nova


def record_analysis(case: PrecedentCase, user, texto: str, fact_roots: list[PrecedentFact]) -> PrecedentAnalysis:
    """FR-010: associa sempre à linha-raiz do grupo — resolve mesmo se receber uma
    versão corrigida por engano, nunca associa a versão errada silenciosamente."""
    analysis = PrecedentAnalysis.objects.create(case=case, created_by=user, texto=texto)
    raiz_ids = {fact.root_id or fact.pk for fact in fact_roots}
    if raiz_ids:
        analysis.facts.set(PrecedentFact.objects.filter(pk__in=raiz_ids))
    return analysis
