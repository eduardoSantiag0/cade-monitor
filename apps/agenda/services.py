"""
Orquestração do app agenda (spec 011): sincronização do calendário oficial,
convites de calendário para os prazos "do escritório", e o auto-encerramento de
processos sem movimentação após a certidão de trânsito em julgado.

Chamadas pelo `run_worker._run_cycle`, nessa ordem (contracts/agenda.md):
`sync_calendar` → `refresh_timelines_and_invites` → `run_auto_closure` — a ordem
importa: o calendário precisa estar pronto antes do cálculo de prazo, e convites
pendentes precisam ser cancelados antes de qualquer apagamento (FR-019).

Nenhuma das três funções lança exceção para o chamador — falha por processo é
logada e não interrompe os demais (mesma garantia das features 009/010).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from . import calendar_source as cs
from . import deadlines as dl
from .ics import build_ics
from .models import ProcessInvite

logger = logging.getLogger(__name__)

# Só estes dois prazos geram convite de calendário (FR-012) — os demais são só
# informativos na linha do tempo (terceiro interessado, recurso/avocação).
_INVITE_DEADLINE_TYPES = {
    'analise_sg': ProcessInvite.DeadlineType.SG_ANALYSIS,
    'certidao_final': ProcessInvite.DeadlineType.FINAL_CERTIFICATE,
}
_INVITE_SUMMARIES = {
    ProcessInvite.DeadlineType.SG_ANALYSIS: 'Prazo de análise da SG',
    ProcessInvite.DeadlineType.FINAL_CERTIFICATE: 'Certidão de trânsito em julgado',
}


def sync_calendar(now: datetime) -> None:
    """FR-003: mantém o calendário do ano corrente e do seguinte (cobre a virada
    de ano). Nunca lança exceção — `sync_calendar_year` já garante isso."""
    year = timezone.localtime(now).year if timezone.is_aware(now) else now.year
    for target_year in (year, year + 1):
        try:
            cs.sync_calendar_year(target_year, settings.REQUEST_TIMEOUT_SECONDS, settings.USER_AGENT)
        except Exception as exc:  # noqa: BLE001 — nunca derruba o ciclo do worker
            logger.error('[agenda] Erro ao sincronizar calendário %s: %s', target_year, exc, exc_info=True)


def _eligible_ac_sumario_processes():
    from apps.processes.models import MonitoredProcess, ProcessStatus
    return MonitoredProcess.objects.filter(status=ProcessStatus.ACTIVE).exclude(last_text='')


def _eligible_subscribers(process):
    """Mesmo critério de elegibilidade de `apps.notifications.services.
    create_notifications_for_change` — reaproveita `ProcessSubscription` por
    composição, sem lista própria (plan.md)."""
    from apps.subscribers.models import ProcessSubscription

    subscriptions = ProcessSubscription.objects.filter(process=process).select_related('subscriber')
    for sub in subscriptions:
        subscriber = sub.subscriber
        if sub.paused or not subscriber.is_reachable():
            continue
        if sub.email_enabled and subscriber.email_enabled and subscriber.email:
            yield subscriber


def _send_invite(process, subscriber, deadline_type: str, uid: str, sequence: int,
                  method: str, event_date, is_estimate: bool) -> tuple[str, str | None]:
    from apps.notifications.channels.email import send_email_notification

    summary = f'{_INVITE_SUMMARIES[deadline_type]} — {process.label}'
    ics_bytes = build_ics(uid, sequence, method, summary, event_date)
    action = 'Cancelamento' if method == 'CANCEL' else 'Convite'
    body = f'{action} de calendário: {summary} ({event_date:%d/%m/%Y}).'
    return send_email_notification(
        subscriber.email, f'[CADE Monitor] {summary}', body,
        attachments=[{
            'filename': 'convite.ics', 'content_type': 'text/calendar',
            'content': ics_bytes, 'calendar_method': method,
        }],
    )


def refresh_timelines_and_invites(now: datetime) -> dict:
    """User Story 2: para cada processo AC sumário ativo, monta a linha do tempo
    e decide REQUEST novo/atualizado, CANCEL, ou nada, para os 2 prazos com
    convite (FR-012 a FR-016). Nunca lança exceção para o chamador."""
    sent = failed = 0
    for process in _eligible_ac_sumario_processes():
        try:
            timeline = dl.monta_linha_do_tempo(process)
        except Exception as exc:  # noqa: BLE001 — falha por processo não trava os demais
            logger.error('[agenda] Erro ao montar linha do tempo do processo #%s: %s',
                         process.pk, exc, exc_info=True)
            continue

        current_by_type = {
            deadline_type: item for item in timeline
            if (deadline_type := _INVITE_DEADLINE_TYPES.get(item['tipo'])) and not item['pendente']
        }

        for deadline_type in _INVITE_DEADLINE_TYPES.values():
            existing = ProcessInvite.objects.filter(process=process, deadline_type=deadline_type).first()
            item = current_by_type.get(deadline_type)

            if item is None:
                if existing and existing.status == ProcessInvite.Status.SENT:
                    result = _dispatch_cancel(process, existing)
                    sent += result[0]
                    failed += result[1]
                continue

            if existing and existing.status == ProcessInvite.Status.SENT and \
                    existing.event_date == item['vencimento'] and existing.is_estimate == item['estimado']:
                continue  # FR-014: nada mudou, não reenvia

            result = _dispatch_request(process, deadline_type, item, existing)
            sent += result[0]
            failed += result[1]

    return {'sent': sent, 'failed': failed}


def _dispatch_request(process, deadline_type, item, existing: ProcessInvite | None) -> tuple[int, int]:
    uid = f'ac-{process.pk}-{deadline_type}@cade-monitor'
    sequence = (existing.sequence + 1) if existing else 0
    sent = failed = 0
    for subscriber in _eligible_subscribers(process):
        status, error = _send_invite(
            process, subscriber, deadline_type, uid, sequence, 'REQUEST',
            item['vencimento'], item['estimado'],
        )
        if status == 'sent':
            sent += 1
        else:
            failed += 1
            logger.warning('[agenda] Falha ao enviar convite para %s: %s', subscriber.email, error)
    ProcessInvite.objects.update_or_create(
        process=process, deadline_type=deadline_type,
        defaults={
            'uid': uid, 'event_date': item['vencimento'], 'sequence': sequence,
            'status': ProcessInvite.Status.SENT, 'is_estimate': item['estimado'],
        },
    )
    return sent, failed


def _dispatch_cancel(process, existing: ProcessInvite) -> tuple[int, int]:
    sent = failed = 0
    for subscriber in _eligible_subscribers(process):
        status, error = _send_invite(
            process, subscriber, existing.deadline_type, existing.uid, existing.sequence + 1,
            'CANCEL', existing.event_date, existing.is_estimate,
        )
        if status == 'sent':
            sent += 1
        else:
            failed += 1
            logger.warning('[agenda] Falha ao enviar cancelamento para %s: %s', subscriber.email, error)
    existing.status = ProcessInvite.Status.CANCELLED
    existing.sequence += 1
    existing.save(update_fields=['status', 'sequence', 'updated_at'])
    return sent, failed


def _cancel_pending_invites(process) -> None:
    """FR-019: cancela qualquer convite pendente ANTES do apagamento — nunca deixa
    um compromisso "fantasma" sem explicação no calendário do assinante."""
    for invite in ProcessInvite.objects.filter(process=process, status=ProcessInvite.Status.SENT):
        _dispatch_cancel(process, invite)


def run_auto_closure(now: datetime) -> dict:
    """User Story 3 (FR-017 a FR-020): apaga processos AC sumário com certidão de
    trânsito em julgado (confiança alta) e >= AGENDA_AUTO_CLOSURE_DAYS dias sem
    nova movimentação, só quando as 4 guardas de segurança passam. Ação
    destrutiva e irreversível — confirmada explicitamente com o dono do
    projeto (spec.md, Assumptions). Nunca lança exceção para o chamador."""
    from apps.monitoring.models import DetectedChange

    deleted = 0
    for process in _eligible_ac_sumario_processes():
        try:
            timeline = dl.monta_linha_do_tempo(process)
        except Exception as exc:  # noqa: BLE001
            logger.error('[agenda] Erro ao avaliar auto-encerramento do processo #%s: %s',
                         process.pk, exc, exc_info=True)
            continue

        certidao = next((i for i in timeline if i['tipo'] == 'certidao_final' and not i['estimado']), None)

        # As 4 guardas de FR-017/FR-018, explícitas e nomeadas — todas MUST ser
        # verdadeiras (`and`), nunca fail-open: dado ausente/insuficiente nunca
        # vira "pode apagar".
        guarda_certidao_confianca_alta = bool(certidao) and certidao['confidence'] >= 0.8
        guarda_sem_erro_na_ultima_checagem = not process.last_error
        guarda_checagem_recente = bool(process.last_checked_at) and (
            now - process.last_checked_at <= timedelta(seconds=settings.AGENDA_LAST_CHECK_MAX_AGE_SECONDS)
        )

        guarda_sem_movimentacao_recente = False
        if guarda_certidao_confianca_alta:
            marco = certidao['vencimento']
            ultima_mudanca = (
                DetectedChange.objects.filter(process=process, detected_at__date__gt=marco)
                .order_by('-detected_at').first()
            )
            referencia = ultima_mudanca.detected_at.date() if ultima_mudanca else marco
            dias_sem_movimentacao = (now.date() - referencia).days
            guarda_sem_movimentacao_recente = dias_sem_movimentacao >= settings.AGENDA_AUTO_CLOSURE_DAYS

        pode_apagar = (
            guarda_certidao_confianca_alta
            and guarda_sem_movimentacao_recente
            and guarda_sem_erro_na_ultima_checagem
            and guarda_checagem_recente
        )
        if not pode_apagar:
            continue

        logger.info(
            '[agenda] Auto-encerramento do processo #%s (%s): certidão=%s confiança=%.2f '
            'dias_sem_movimentacao>=%s last_error_vazio=%s last_checked_at=%s',
            process.pk, process.label, certidao['vencimento'], certidao['confidence'],
            settings.AGENDA_AUTO_CLOSURE_DAYS, guarda_sem_erro_na_ultima_checagem, process.last_checked_at,
        )
        try:
            _cancel_pending_invites(process)
        except Exception as exc:  # noqa: BLE001 — mesmo com falha de e-mail, a decisão já foi tomada e logada
            logger.error('[agenda] Erro ao cancelar convites antes do apagamento do processo #%s: %s',
                         process.pk, exc, exc_info=True)
        process.delete()
        deleted += 1

    return {'deleted': deleted}
