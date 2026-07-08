from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localtime
from django.views.decorators.http import require_POST

from apps.monitoring.models import CheckRun, DetectedChange

from .forms import ProcessForm
from .models import MonitoredProcess, ProcessStatus
from .selectors import get_all_processes, get_filtered_processes
from .services import create_process, update_process_status


def _format_process_last_update(process: MonitoredProcess) -> str:
    last_update = process.last_changed_at or process.last_checked_at or process.updated_at
    if not last_update:
        return 'Nao disponivel'
    return localtime(last_update).strftime('%d/%m/%Y %H:%M')


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
@require_POST
def process_notify_subscribers(request, pk):
    """Envia aviso manual para assinantes do processo conforme preferências por canal."""
    process = get_object_or_404(MonitoredProcess, pk=pk)
    subscriptions = process.subscriptions.select_related('subscriber').all()

    from apps.notifications.channels.email import send_email_notification
    from apps.notifications.channels.evolution import send_whatsapp_notification

    sent_email = 0
    sent_whatsapp = 0
    failed_email = 0
    failed_whatsapp = 0

    subject = f'[CADE Monitor] Aviso manual: {process.label}'[:180]
    last_update_text = _format_process_last_update(process)
    email_body = (
        'Este e um envio manual feito pela tela de detalhes do processo no CADE Monitor.\n\n'
        f'Processo: {process.label}\n'
        f'URL: {process.effective_url}\n\n'
        'Se recebeu este aviso, suas preferencias de notificacao para este processo estao ativas.'
    )
    whatsapp_body = (
        '📢 *CADE Monitor*\n'
        'Envio manual para assinantes do processo.\n\n'
        f'📁 *Processo:* {process.label}\n'
        f'🔗 *Link do processo:* {process.effective_url}\n'
        f'🕒 *Ultima atualizacao:* {last_update_text}\n\n'
        '✅ Se recebeu este aviso, suas preferencias de notificacao estao ativas.'
    )

    for subscription in subscriptions:
        subscriber = subscription.subscriber
        if not subscriber.is_reachable():
            continue

        if subscription.email_enabled and subscriber.email_enabled and subscriber.email:
            status, _error = send_email_notification(
                to_address=subscriber.email,
                subject=subject,
                body=email_body,
            )
            if status == 'sent':
                sent_email += 1
            else:
                failed_email += 1

        if (
            settings.EVOLUTION_ENABLED
            and subscription.whatsapp_enabled
            and subscriber.whatsapp_enabled
            and subscriber.phone
        ):
            status, _error = send_whatsapp_notification(
                phone=subscriber.phone,
                body=whatsapp_body,
            )
            if status == 'sent':
                sent_whatsapp += 1
            else:
                failed_whatsapp += 1

    if (sent_email + sent_whatsapp + failed_email + failed_whatsapp) == 0:
        messages.warning(
            request,
            'Nenhum assinante elegivel para envio manual neste processo.',
        )
    else:
        messages.success(
            request,
            (
                'Envio manual concluido. '
                f'E-mail enviados: {sent_email}, falhas: {failed_email}. '
                f'WhatsApp enviados: {sent_whatsapp}, falhas: {failed_whatsapp}.'
            ),
        )

    return redirect('processes:detail', pk=pk)


@login_required
@require_POST
def process_send_test_whatsapp(request, pk):
    """Envia WhatsApp de teste para assinantes elegiveis do processo."""
    process = get_object_or_404(MonitoredProcess, pk=pk)
    subscriptions = process.subscriptions.select_related('subscriber').all()

    from apps.notifications.channels.evolution import send_whatsapp_notification

    last_update_text = _format_process_last_update(process)
    template_body = (
        '🧪 *Teste de WhatsApp - CADE Monitor*\n\n'
        'Este e um envio de teste feito pela tela de detalhes do processo.\n\n'
        f'📁 *Processo:* {process.label}\n'
        f'🔗 *Link do processo:* {process.effective_url}\n'
        f'🕒 *Ultima atualizacao:* {last_update_text}\n\n'
        '✅ Se recebeu esta mensagem, o canal de WhatsApp esta funcionando.'
    )

    sent_whatsapp = 0
    failed_whatsapp = 0
    failure_details: list[str] = []

    for subscription in subscriptions:
        subscriber = subscription.subscriber
        if not subscriber.is_reachable():
            continue

        if (
            settings.EVOLUTION_ENABLED
            and subscriber.whatsapp_enabled
            and subscriber.phone
        ):
            status, _error = send_whatsapp_notification(
                phone=subscriber.phone,
                body=template_body,
            )
            if status == 'sent':
                sent_whatsapp += 1
            else:
                failed_whatsapp += 1
                if _error:
                    failure_details.append(f'{subscriber.name}: {_error}')

    if (sent_whatsapp + failed_whatsapp) == 0:
        messages.warning(
            request,
            'Nenhum assinante com WhatsApp habilitado neste processo para envio de teste.',
        )
    else:
        detail = ''
        if failure_details:
            detail = f' Detalhes: {" | ".join(failure_details[:3])}'
        messages.success(
            request,
            (
                f'WhatsApp teste concluido. Enviados: {sent_whatsapp}. '
                f'Falhas: {failed_whatsapp}.{detail}'
            ),
        )

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
