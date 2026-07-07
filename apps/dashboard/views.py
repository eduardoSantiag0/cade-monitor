from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.monitoring.models import DetectedChange
from apps.notifications.models import Notification, NotificationStatus
from apps.processes.models import MonitoredProcess, ProcessStatus
from apps.processes.selectors import get_all_processes, get_dashboard_stats
from apps.subscribers.models import Subscriber


@login_required
def index(request):
    processes = get_all_processes()
    recent_changes = (
        DetectedChange.objects
        .select_related('process')
        .order_by('-detected_at')[:10]
    )
    stats = get_dashboard_stats()
    return render(request, 'dashboard/index.html', {
        'processes': processes[:20],
        'recent_changes': recent_changes,
        'stats': stats,
    })


@login_required
def notifications_list(request):
    status_filter = request.GET.get('status', '')
    qs = (
        Notification.objects
        .select_related('change', 'change__process', 'subscriber')
        .order_by('-created_at')
    )
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, 'notifications/list.html', {
        'notifications': qs[:100],
        'status_filter': status_filter,
        'status_choices': NotificationStatus.choices,
    })


def _get_test_email_destination() -> str:
    subscriber = (
        Subscriber.objects
        .filter(email_enabled=True)
        .exclude(email='')
        .order_by('id')
        .first()
    )
    return (subscriber.email or '').strip() if subscriber else ''


def _get_test_whatsapp_destination() -> str:
    subscriber = (
        Subscriber.objects
        .filter(whatsapp_enabled=True)
        .exclude(phone='')
        .order_by('id')
        .first()
    )
    return (subscriber.phone or '').strip() if subscriber else ''


@login_required
@require_POST
def send_test_email(request):
    from apps.notifications.channels.email import send_email_notification

    destination = _get_test_email_destination()
    if not destination:
        messages.error(
            request,
            'Nenhum assinante com e-mail habilitado foi encontrado para teste.',
        )
        return redirect('dashboard:notifications')

    subject = '[CADE Monitor] Teste de envio de e-mail'
    body = (
        'Esta e uma mensagem de teste enviada pela tela de notificacoes do CADE Monitor.\n\n'
        'Se voce recebeu este aviso, o canal de e-mail esta funcionando.'
    )

    status, error = send_email_notification(to_address=destination, subject=subject, body=body)
    if status == 'sent':
        messages.success(request, f'E-mail de teste enviado para {destination}.')
    else:
        detail = f' Detalhe: {error}' if error else ''
        messages.error(request, f'Falha ao enviar e-mail de teste para {destination}.{detail}')

    return redirect('dashboard:notifications')


@login_required
@require_POST
def send_test_whatsapp(request):
    from apps.notifications.channels.evolution import send_whatsapp_notification

    destination = _get_test_whatsapp_destination()
    if not destination:
        messages.error(
            request,
            'Nenhum assinante com WhatsApp habilitado foi encontrado para teste.',
        )
        return redirect('dashboard:notifications')

    body = (
        'CADE Monitor: esta e uma mensagem de teste enviada pela tela de notificacoes.\n\n'
        'Se chegou aqui, o canal WhatsApp esta funcionando.'
    )

    status, error = send_whatsapp_notification(phone=destination, body=body)
    if status == 'sent':
        messages.success(request, f'Mensagem de teste enviada para {destination}.')
    else:
        detail = f' Detalhe: {error}' if error else ''
        messages.error(request, f'Falha ao enviar WhatsApp de teste para {destination}.{detail}')

    return redirect('dashboard:notifications')
