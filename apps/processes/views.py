from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localtime
from django.views.decorators.http import require_POST

from apps.monitoring.extractors import extract_protocol_records
from apps.monitoring.models import CheckRun, DetectedChange

from .forms import ProcessForm
from .models import MonitoredProcess, ProcessStatus
from .selectors import get_all_processes, get_filtered_processes
from .services import (
    ManualDispatchChannel,
    create_process,
    dispatch_manual_notifications,
    update_process_status,
)


def _format_process_last_update(process: MonitoredProcess) -> str:
    last_update = process.last_changed_at or process.last_checked_at or process.updated_at
    if not last_update:
        return 'Nao disponivel'
    return localtime(last_update).strftime('%d/%m/%Y %H:%M')


def _latest_protocol_record(change: DetectedChange) -> dict | None:
    """Retorna o protocolo mais recente da lista do snapshot novo da mudança."""
    snapshot_text = ''
    if change.new_snapshot and change.new_snapshot.text_content:
        snapshot_text = change.new_snapshot.text_content

    return _latest_protocol_record_from_text(snapshot_text)


def _latest_protocol_record_from_text(snapshot_text: str) -> dict | None:
    """Retorna o protocolo mais recente da lista a partir de texto extraído."""
    if not snapshot_text:
        return None

    records = extract_protocol_records(snapshot_text)
    if not records:
        return None

    return max(
        records,
        key=lambda item: (
            str(item.get('sort_key') or ''),
            str(item.get('registry_date') or ''),
            str(item.get('document') or ''),
        ),
    )


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
def process_send_test_email(request, pk):
    """Envia e-mail de teste para assinantes elegiveis do processo."""
    process = get_object_or_404(MonitoredProcess, pk=pk)
    subscriptions = process.subscriptions.select_related('subscriber').all()

    from apps.notifications.channels.email import send_email_notification
    from apps.notifications.services import build_test_notification_body

    subject = f'[CADE Monitor] Teste de e-mail: {process.label}'[:180]
    template_body = build_test_notification_body(
        process_label=process.label,
        process_url=process.effective_url,
        channel='email',
    )

    # Mantém o teste de e-mail alinhado ao teste de WhatsApp: basta o
    # assinante ter o canal global ativo e endereço válido (não exige o
    # toggle por processo, diferente do aviso manual).
    stats = dispatch_manual_notifications(subscriptions, [
        ManualDispatchChannel(
            name='email',
            is_eligible=lambda sub: sub.subscriber.email_enabled and bool(sub.subscriber.email),
            send=lambda subscriber: send_email_notification(
                to_address=subscriber.email, subject=subject, body=template_body,
            ),
        ),
    ])
    sent_email = stats['email']['sent']
    failed_email = stats['email']['failed']
    failure_details = stats['email']['failure_details']

    if (sent_email + failed_email) == 0:
        messages.warning(
            request,
            'Nenhum assinante com e-mail habilitado neste processo para envio de teste.',
        )
    else:
        detail = ''
        if failure_details:
            detail = f' Detalhes: {" | ".join(failure_details[:3])}'
        messages.success(
            request,
            (
                f'E-mail teste concluido. Enviados: {sent_email}. '
                f'Falhas: {failed_email}.{detail}'
            ),
        )

    return redirect('processes:detail', pk=pk)


@login_required
@require_POST
def process_notify_subscribers(request, pk):
    """Envia aviso manual para assinantes do processo conforme preferências por canal."""
    process = get_object_or_404(MonitoredProcess, pk=pk)
    subscriptions = process.subscriptions.select_related('subscriber').all()

    from apps.notifications.channels.email import send_email_notification
    from apps.notifications.channels.evolution import send_whatsapp_notification

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

    stats = dispatch_manual_notifications(subscriptions, [
        ManualDispatchChannel(
            name='email',
            is_eligible=lambda sub: sub.email_enabled and sub.subscriber.email_enabled and bool(sub.subscriber.email),
            send=lambda subscriber: send_email_notification(
                to_address=subscriber.email, subject=subject, body=email_body,
            ),
        ),
        ManualDispatchChannel(
            name='whatsapp',
            is_eligible=lambda sub: (
                settings.EVOLUTION_ENABLED
                and sub.whatsapp_enabled
                and sub.subscriber.whatsapp_enabled
                and bool(sub.subscriber.phone)
            ),
            send=lambda subscriber: send_whatsapp_notification(phone=subscriber.phone, body=whatsapp_body),
        ),
    ])
    sent_email = stats['email']['sent']
    failed_email = stats['email']['failed']
    sent_whatsapp = stats['whatsapp']['sent']
    failed_whatsapp = stats['whatsapp']['failed']

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
    from apps.notifications.services import build_test_notification_body

    template_body = build_test_notification_body(
        process_label=process.label,
        process_url=process.effective_url,
        channel='whatsapp',
    )

    # Igual ao teste de e-mail: basta o toggle global do assinante, sem
    # exigir o toggle por processo.
    stats = dispatch_manual_notifications(subscriptions, [
        ManualDispatchChannel(
            name='whatsapp',
            is_eligible=lambda sub: (
                settings.EVOLUTION_ENABLED and sub.subscriber.whatsapp_enabled and bool(sub.subscriber.phone)
            ),
            send=lambda subscriber: send_whatsapp_notification(phone=subscriber.phone, body=template_body),
        ),
    ])
    sent_whatsapp = stats['whatsapp']['sent']
    failed_whatsapp = stats['whatsapp']['failed']
    failure_details = stats['whatsapp']['failure_details']

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
@require_POST
def process_send_latest_update(request, pk):
    """Envia a última atualização detectada para assinantes elegíveis do processo."""
    process = get_object_or_404(MonitoredProcess, pk=pk)
    subscriptions = process.subscriptions.select_related('subscriber').all()
    latest_change = process.changes.order_by('-detected_at').first()
    snapshot_text = ''
    if latest_change and latest_change.new_snapshot and latest_change.new_snapshot.text_content:
        snapshot_text = latest_change.new_snapshot.text_content
    elif process.last_text:
        snapshot_text = process.last_text

    if not snapshot_text:
        messages.warning(request, 'Este processo ainda não possui dados de atualização para envio.')
        return redirect('processes:detail', pk=pk)

    from apps.monitoring.clients import FetchError, download_document
    from apps.notifications.channels.email import send_email_notification
    from apps.notifications.channels.evolution import send_whatsapp_attachment, send_whatsapp_notification

    reference_dt = (
        latest_change.detected_at
        if latest_change
        else (process.last_changed_at or process.last_checked_at or process.updated_at)
    )
    detected_at = localtime(reference_dt).strftime('%d/%m/%Y %H:%M')
    subject = f'[CADE Monitor] Última atualização: {process.label}'[:180]
    protocol = _latest_protocol_record_from_text(snapshot_text)
    first_document = None
    if latest_change and protocol and protocol.get('document'):
        first_document = (
            latest_change.documents
            .filter(document_number=str(protocol.get('document') or ''))
            .order_by('created_at', 'id')
            .first()
        )
    if latest_change and first_document is None:
        first_document = latest_change.documents.order_by('created_at', 'id').first()

    first_doc_label = 'Não identificado'
    first_doc_url = ''
    email_attachments: list[dict[str, object]] = []
    attachment_warning = ''

    if protocol:
        first_doc_label = ' '.join(
            part for part in [
                str(protocol.get('document') or '').strip(),
                str(protocol.get('doc_type') or '').strip(),
                str(protocol.get('doc_date') or '').strip(),
                str(protocol.get('registry_date') or '').strip(),
                str(protocol.get('unit') or '').strip(),
            ]
            if part
        ).strip() or 'Não identificado'

    if first_document:
        if not protocol:
            first_doc_label = f'{first_document.title} {first_document.document_number}'.strip()
        first_doc_url = first_document.url or ''

        if first_document.mode == 'attachment' and first_doc_url:
            try:
                email_attachments.append(
                    download_document(
                        url=first_doc_url,
                        record={
                            'document': first_document.document_number,
                            'doc_type': first_document.title,
                        },
                        timeout=settings.REQUEST_TIMEOUT_SECONDS,
                        user_agent=settings.USER_AGENT,
                        max_bytes=int(getattr(settings, 'EMAIL_ATTACHMENT_MAX_BYTES', 8 * 1024 * 1024)),
                    )
                )
            except FetchError as exc:
                attachment_warning = f'Não foi possível anexar o PDF automaticamente ({exc}).'
        elif first_doc_url:
            attachment_warning = 'Documento classificado como somente link; PDF não anexado automaticamente.'
    elif not protocol:
        attachment_warning = 'Nenhum protocolo detectado para anexar nesta atualização.'

    attachment_status = 'PDF associado em anexo.' if email_attachments else (attachment_warning or 'PDF não disponível.')
    summary_text = (
        latest_change.summary
        if latest_change
        else f'Último protocolo identificado: {first_doc_label}'
    )

    email_body = (
        f'Nome do Processo: {process.label}\n\n'
        'Última atualização detectada no processo.\n\n'
        f'Primeira linha da Lista de Protocolos:\n{first_doc_label}\n\n'
        f'Link do protocolo/PDF:\n{first_doc_url or "Não disponível"}\n\n'
        f'Status do PDF: {attachment_status}\n\n'
        f'Resumo:\n{summary_text}\n\n'
        'Processo no SEI/CADE:\n'
        f'{process.effective_url}\n\n'
        f'Detectado em: {detected_at}'
    )
    whatsapp_body = (
        f'📁 Nome do Processo: {process.label}\n\n'
        '📣 Última atualização detectada no processo.\n\n'
        f'📄 Primeiro protocolo: {first_doc_label}\n'
        f'🔗 PDF/Documento: {first_doc_url or "Não disponível"}\n\n'
        f'📝 Resumo: {summary_text[:600]}\n\n'
        f'🔗 Processo no SEI/CADE:\n{process.effective_url}\n\n'
        f'🕒 Detectado em: {detected_at}'
    )

    def _send_whatsapp_with_attachment(subscriber) -> tuple[str, str | None]:
        """Envia a mensagem principal e, se houver PDF, o anexo em seguida —
        conta como uma tentativa só por assinante, resultado do último passo."""
        status, error = send_whatsapp_notification(phone=subscriber.phone, body=whatsapp_body)
        if status != 'sent':
            return status, error
        if not first_doc_url:
            return 'sent', None
        return send_whatsapp_attachment(
            phone=subscriber.phone,
            media_url=first_doc_url,
            file_name=(first_doc_label or 'documento')[:140],
        )

    stats = dispatch_manual_notifications(subscriptions, [
        ManualDispatchChannel(
            name='email',
            is_eligible=lambda sub: sub.email_enabled and sub.subscriber.email_enabled and bool(sub.subscriber.email),
            send=lambda subscriber: send_email_notification(
                to_address=subscriber.email, subject=subject, body=email_body, attachments=email_attachments,
            ),
        ),
        ManualDispatchChannel(
            name='whatsapp',
            is_eligible=lambda sub: (
                settings.EVOLUTION_ENABLED
                and sub.whatsapp_enabled
                and sub.subscriber.whatsapp_enabled
                and bool(sub.subscriber.phone)
            ),
            send=_send_whatsapp_with_attachment,
        ),
    ])
    sent_email = stats['email']['sent']
    failed_email = stats['email']['failed']
    sent_whatsapp = stats['whatsapp']['sent']
    failed_whatsapp = stats['whatsapp']['failed']

    if (sent_email + sent_whatsapp + failed_email + failed_whatsapp) == 0:
        messages.warning(
            request,
            'Nenhum assinante elegivel para envio da última atualização neste processo.',
        )
    else:
        messages.success(
            request,
            (
                'Última atualização enviada. '
                f'E-mail enviados: {sent_email}, falhas: {failed_email}. '
                f'WhatsApp enviados: {sent_whatsapp}, falhas: {failed_whatsapp}.'
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
