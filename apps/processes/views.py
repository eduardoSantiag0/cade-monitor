from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.monitoring.models import CheckRun, DetectedChange

from .forms import ProcessForm
from .models import MonitoredProcess, ProcessStatus
from .selectors import get_all_processes, get_filtered_processes
from .services import create_process, update_process_status


@login_required
def process_list(request):
    status_filter = request.GET.get('status', '')
    processes = get_filtered_processes(status_filter)
    return render(request, 'processes/list.html', {
        'processes': processes,
        'status_filter': status_filter,
        'status_choices': ProcessStatus.choices,
    })


@login_required
def process_detail(request, pk):
    process = get_object_or_404(MonitoredProcess, pk=pk)

    changes_qs = DetectedChange.objects.filter(process=process).order_by('-detected_at')
    paginator = Paginator(changes_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    recent_runs = CheckRun.objects.filter(process=process).order_by('-started_at')[:10]
    subscriptions = process.subscriptions.select_related('subscriber').all()
    return render(request, 'processes/detail.html', {
        'process': process,
        'page_obj': page_obj,
        'recent_runs': recent_runs,
        'subscriptions': subscriptions,
    })


@login_required
def process_create(request):
    if request.method == 'POST':
        form = ProcessForm(request.POST)
        if form.is_valid():
            process = create_process(
                label=form.cleaned_data['label'],
                source=form.cleaned_data['source'],
                check_interval_seconds=form.cleaned_data.get('check_interval_seconds'),
                notes=form.cleaned_data.get('notes', ''),
            )
            messages.success(request, f'Processo "{process.label}" cadastrado com sucesso.')
            return redirect('processes:detail', pk=process.pk)
    else:
        form = ProcessForm()
    return render(request, 'processes/form.html', {'form': form, 'title': 'Cadastrar processo'})


@login_required
def process_edit(request, pk):
    process = get_object_or_404(MonitoredProcess, pk=pk)
    if request.method == 'POST':
        form = ProcessForm(request.POST, instance=process)
        if form.is_valid():
            form.save()
            messages.success(request, 'Processo atualizado.')
            return redirect('processes:detail', pk=process.pk)
    else:
        form = ProcessForm(instance=process)
    return render(request, 'processes/form.html', {
        'form': form,
        'process': process,
        'title': 'Editar processo',
    })


@login_required
def process_toggle(request, pk):
    """Alterna o status entre ACTIVE e PAUSED."""
    if request.method == 'POST':
        process = get_object_or_404(MonitoredProcess, pk=pk)
        new_status = ProcessStatus.PAUSED if process.status == ProcessStatus.ACTIVE else ProcessStatus.ACTIVE
        update_process_status(process, new_status)
        label = process.get_status_display()
        messages.success(request, f'Processo "{process.label}" agora está {label}.')
    return redirect('processes:list')


@login_required
def process_check_now(request, pk):
    """Executa uma checagem imediata do processo (ação manual)."""
    if request.method == 'POST':
        process = get_object_or_404(MonitoredProcess, pk=pk)
        from apps.monitoring.services import run_check
        result = run_check(process)
        if result.get('changed'):
            messages.warning(request, f'Mudança detectada: {result["message"][:200]}')
        elif result.get('ok'):
            messages.success(request, f'Verificação concluída: {result["message"]}')
        else:
            messages.error(request, f'Erro: {result["message"]}')
    return redirect('processes:detail', pk=pk)


@login_required
def change_detail(request, pk):
    """Exibe o antes/depois de uma mudança detectada."""
    change = get_object_or_404(
        DetectedChange.objects.select_related('process', 'old_snapshot', 'new_snapshot'),
        pk=pk,
    )
    return render(request, 'processes/change_detail.html', {'change': change})


@login_required
def change_review(request, pk):
    """Registra a revisão humana de uma mudança."""
    if request.method == 'POST':
        change = get_object_or_404(DetectedChange, pk=pk)
        review = request.POST.get('review', '')
        notes = request.POST.get('reviewer_notes', '')
        from apps.monitoring.models import ChangeReview
        valid_reviews = [c[0] for c in ChangeReview.choices]
        if review in valid_reviews:
            change.review = review
            change.reviewer_notes = notes[:2000]
            change.save(update_fields=['review', 'reviewer_notes'])
            messages.success(request, 'Revisão registrada.')
        else:
            messages.error(request, 'Tipo de revisão inválido.')
    return redirect('processes:change_detail', pk=pk)
