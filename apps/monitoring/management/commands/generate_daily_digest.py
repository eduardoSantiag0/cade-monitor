"""
Gera e envia um resumo diário das mudanças detectadas nas últimas N horas.

Ideal para rodar via cron toda manhã (ex: 8h) ou via Docker Compose.
O comando agrupa mudanças por processo e envia um único digest por assinante,
evitando spam de notificações individuais.

Uso:
    python manage.py generate_daily_digest
    python manage.py generate_daily_digest --hours 48
    python manage.py generate_daily_digest --dry-run
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Envia resumo diário das mudanças detectadas para todos os assinantes ativos.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Janela de tempo em horas a considerar (padrão: 24).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Exibe o que seria enviado sem realmente enviar.',
        )

    def handle(self, *args, **options):
        hours = options['hours']
        dry_run = options['dry_run']
        since = timezone.now() - timedelta(hours=hours)

        from apps.monitoring.models import DetectedChange
        from apps.subscribers.models import Subscriber

        recent_changes = (
            DetectedChange.objects
            .filter(detected_at__gte=since)
            .select_related('process')
            .order_by('process_id', '-detected_at')
        )

        if not recent_changes.exists():
            self.stdout.write(f'Nenhuma mudança nas últimas {hours}h. Digest não enviado.')
            return

        # Agrupa mudanças por processo
        changes_by_process: dict[int, dict] = {}
        for change in recent_changes:
            pid = change.process_id
            if pid not in changes_by_process:
                changes_by_process[pid] = {'process': change.process, 'changes': []}
            changes_by_process[pid]['changes'].append(change)

        self.stdout.write(
            f'{len(changes_by_process)} processo(s) com mudanças nas últimas {hours}h.'
        )

        notified = 0
        for subscriber in Subscriber.objects.all():
            if not subscriber.is_reachable():
                continue

            subscribed_ids = set(subscriber.subscriptions.values_list('process_id', flat=True))
            relevant = [
                entry for pid, entry in changes_by_process.items()
                if pid in subscribed_ids
            ]
            if not relevant:
                continue

            body = _build_digest_body(subscriber.name, relevant, hours)

            if dry_run:
                self.stdout.write(f'\n[DRY-RUN] Para: {subscriber.name}')
                self.stdout.write(body[:500])
                self.stdout.write('...')
            else:
                self._send(subscriber, body, hours)
                logger.info('[digest] Digest enviado para %s.', subscriber.name)

            notified += 1

        label = 'simulado' if dry_run else 'enviado'
        self.stdout.write(
            self.style.SUCCESS(f'Digest {label} para {notified} assinante(s).')
        )

    def _send(self, subscriber, body: str, hours: int) -> None:
        subject = f'[CADE Monitor] Resumo das últimas {hours}h'

        if subscriber.email_enabled and subscriber.email:
            from apps.notifications.channels.email import send_email_notification
            status, error = send_email_notification(
                to_address=subscriber.email,
                subject=subject,
                body=body,
            )
            if status != 'sent':
                logger.warning('[digest] Email falhou para %s: %s', subscriber.email, error)

        if subscriber.whatsapp_enabled and subscriber.phone and settings.EVOLUTION_ENABLED:
            from apps.notifications.channels.evolution import send_whatsapp_notification
            status, error = send_whatsapp_notification(
                phone=subscriber.phone,
                body=body,
            )
            if status != 'sent':
                logger.warning('[digest] WhatsApp falhou para %s: %s', subscriber.phone, error)


def _build_digest_body(name: str, relevant_entries: list[dict], hours: int) -> str:
    """Monta a mensagem de digest em linguagem natural."""
    from django.utils.timezone import localtime

    total_changes = sum(len(e['changes']) for e in relevant_entries)
    lines = [
        f'Olá, {name}!',
        '',
        f'Aqui está o resumo das últimas {hours}h no CADE Monitor.',
        f'Foram detectadas {total_changes} mudança(s) em {len(relevant_entries)} processo(s):',
        '',
    ]

    for entry in relevant_entries:
        process = entry['process']
        changes = entry['changes']
        lines.append(f'📋 {process.label}')
        lines.append(f'   {len(changes)} mudança(s) detectada(s)')

        # Exibe até 3 mudanças como prévia
        for change in changes[:3]:
            dt = localtime(change.detected_at).strftime('%d/%m às %H:%M')
            summary_preview = change.summary.replace('\n', ' ')[:120]
            lines.append(f'   • {dt}: {summary_preview}')

        if len(changes) > 3:
            lines.append(f'   ... e mais {len(changes) - 3} mudança(s).')
        lines.append('')

    lines += [
        'Acesse o painel para ver os diffs completos e classificar as mudanças.',
        '',
        'Você recebe este resumo porque está inscrito nestes processos.',
        'Para parar de receber, desative seu cadastro no painel.',
    ]
    return '\n'.join(lines)
