from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import selectors, services
from .forms import (
    PrecedentAnalysisForm, PrecedentCaseForm, PrecedentEntityForm, PrecedentFactCorrectionForm,
    PrecedentFactForm,
)
from .models import PrecedentCase, PrecedentEntity, PrecedentFact


@login_required
def case_list(request):
    cases = PrecedentCase.objects.all()
    form = PrecedentCaseForm()
    return render(request, 'precedentes/list.html', {'cases': cases, 'form': form})


@login_required
@require_POST
def case_create(request):
    form = PrecedentCaseForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Não foi possível criar o caso — confira os dados.')
        return redirect('precedentes:list')
    case = services.create_case(
        request.user, form.cleaned_data['titulo'], form.cleaned_data['cliente'], form.cleaned_data['notas'],
    )
    messages.success(request, f'Caso "{case.titulo}" criado.')
    return redirect('precedentes:case_detail', pk=case.pk)


def _case_context(case: PrecedentCase) -> dict:
    entities = []
    for entity in case.entities.all():
        entities.append({
            'entity': entity,
            'facts': selectors.current_facts(entity),
            'edit_form': PrecedentEntityForm(instance=entity),
        })
    return {
        'case': case,
        'entities': entities,
        'entity_form': PrecedentEntityForm(),
        'fact_form': PrecedentFactForm(),
        'analysis_form': PrecedentAnalysisForm(case=case),
        'analyses': selectors.case_analyses(case),
    }


@login_required
def case_detail(request, pk):
    case = get_object_or_404(PrecedentCase, pk=pk)
    return render(request, 'precedentes/case_detail.html', _case_context(case))


@login_required
@require_POST
def entity_add(request, case_pk):
    case = get_object_or_404(PrecedentCase, pk=case_pk)
    form = PrecedentEntityForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Não foi possível adicionar a empresa — confira os dados.')
        return redirect('precedentes:case_detail', pk=case.pk)
    services.add_entity(
        case, form.cleaned_data['papel'], form.cleaned_data['razao_social'],
        form.cleaned_data['cnpj'], form.cleaned_data['pais'],
    )
    messages.success(request, 'Empresa adicionada.')
    return redirect('precedentes:case_detail', pk=case.pk)


@login_required
@require_POST
def entity_update(request, pk):
    entity = get_object_or_404(PrecedentEntity, pk=pk)
    form = PrecedentEntityForm(request.POST, instance=entity)
    if not form.is_valid():
        messages.error(request, 'Não foi possível atualizar a empresa — confira os dados.')
        return redirect('precedentes:case_detail', pk=entity.case_id)
    services.update_entity(entity, **form.cleaned_data)
    messages.success(request, 'Empresa atualizada.')
    return redirect('precedentes:case_detail', pk=entity.case_id)


@login_required
@require_POST
def entity_remove(request, pk):
    entity = get_object_or_404(PrecedentEntity, pk=pk)
    case_pk = entity.case_id
    nome = entity.razao_social
    services.remove_entity(entity)
    messages.success(request, f'Empresa "{nome}" removida, junto com seus fatos e análises dependentes.')
    return redirect('precedentes:case_detail', pk=case_pk)


@login_required
@require_POST
def fact_add(request, entity_pk):
    entity = get_object_or_404(PrecedentEntity, pk=entity_pk)
    form = PrecedentFactForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Não foi possível registrar o fato — confira os dados.')
        return redirect('precedentes:case_detail', pk=entity.case_id)
    try:
        services.record_fact(entity, request.user, **form.cleaned_data)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('precedentes:case_detail', pk=entity.case_id)
    messages.success(request, 'Fato registrado.')
    return redirect('precedentes:case_detail', pk=entity.case_id)


@login_required
@require_POST
def fact_correct(request, pk):
    fact = get_object_or_404(PrecedentFact, pk=pk)
    form = PrecedentFactCorrectionForm(request.POST, instance=fact)
    if not form.is_valid():
        messages.error(request, 'Não foi possível corrigir o fato — confira os dados (motivo é obrigatório).')
        return redirect('precedentes:case_detail', pk=fact.entity.case_id)
    campos = {k: v for k, v in form.cleaned_data.items() if k != 'motivo'}
    try:
        services.correct_fact(fact, request.user, form.cleaned_data['motivo'], **campos)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('precedentes:case_detail', pk=fact.entity.case_id)
    messages.success(request, 'Fato corrigido — versão anterior preservada no histórico.')
    return redirect('precedentes:case_detail', pk=fact.entity.case_id)


@login_required
def fact_history(request, pk):
    fact = get_object_or_404(PrecedentFact, pk=pk)
    history = selectors.fact_history(fact)
    return render(request, 'precedentes/fact_history.html', {'fact': fact, 'history': history})


@login_required
@require_POST
def analysis_add(request, case_pk):
    case = get_object_or_404(PrecedentCase, pk=case_pk)
    form = PrecedentAnalysisForm(request.POST, case=case)
    if not form.is_valid():
        messages.error(request, 'Não foi possível registrar a análise — selecione ao menos um fato-base.')
        return redirect('precedentes:case_detail', pk=case.pk)
    services.record_analysis(case, request.user, form.cleaned_data['texto'], list(form.cleaned_data['fact_ids']))
    messages.success(request, 'Análise registrada.')
    return redirect('precedentes:case_detail', pk=case.pk)
