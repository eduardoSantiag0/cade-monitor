"""
RunDemoUseCase (spec 014): demonstração controlada do fluxo principal do CADE
Monitor, para fins de portfólio — comando /preview.

Reaproveita a lógica real de diff (`apps.monitoring.diff.compute_diff`) e de
formatação de notificação (`apps.notifications.services.
build_test_notification_body`, já usada pelo botão "enviar e-mail de teste"
do painel). NUNCA chama `get_snapshot`/`collect_new_documents` (rede real) nem
qualquer função de envio real de notificação — o conteúdo é só formatado e
devolvido como texto, nunca despachado.

O processo fictício é um único `MonitoredProcess` reservado, sempre
`status=ARCHIVED` — isso garante que `apps.monitoring.scheduler.
get_due_processes` (filtra por `status=ACTIVE`) nunca o seleciona para uma
checagem real, sem precisar de nenhum filtro adicional.
"""
from __future__ import annotations

from django.utils import timezone

from apps.monitoring.diff import compute_diff
from apps.monitoring.models import CheckRun, CheckStatus, DetectedChange, PageSnapshot
from apps.notifications.services import build_test_notification_body
from apps.processes.models import MonitoredProcess, ProcessStatus

from . import messages

DEMO_PROCESS_SOURCE = '08700.000000/2026-00'
DEMO_PROCESS_LABEL = '[Demonstração] Ato de Concentração fictício'
DEMO_OLD_TEXT = 'Andamento: Processo distribuído para a Superintendência-Geral.'
DEMO_NEW_TEXT = (
    'Andamento: Processo distribuído para a Superintendência-Geral.\n'
    'Andamento: Documento adicionado aos autos.'
)
DEMO_HASH_OLD = 'demo-hash-anterior'
DEMO_HASH_NEW = 'demo-hash-novo'


def _get_or_create_demo_process() -> MonitoredProcess:
    process, _created = MonitoredProcess.objects.get_or_create(
        source=DEMO_PROCESS_SOURCE,
        defaults={
            'label': DEMO_PROCESS_LABEL,
            'status': ProcessStatus.ARCHIVED,
            'last_hash': DEMO_HASH_NEW,
            'last_text': DEMO_NEW_TEXT,
        },
    )
    return process


def _get_or_create_demo_change(process: MonitoredProcess, summary: str, diff_text: str) -> DetectedChange:
    existing = DetectedChange.objects.filter(process=process).first()
    if existing:
        return existing

    check_run = CheckRun.objects.create(process=process, status=CheckStatus.CHANGED)
    old_snapshot = PageSnapshot.objects.create(
        process=process, check_run=check_run, content_hash=DEMO_HASH_OLD, text_content=DEMO_OLD_TEXT,
    )
    new_snapshot = PageSnapshot.objects.create(
        process=process, check_run=check_run, content_hash=DEMO_HASH_NEW, text_content=DEMO_NEW_TEXT,
    )
    return DetectedChange.objects.create(
        process=process, check_run=check_run,
        old_snapshot=old_snapshot, new_snapshot=new_snapshot,
        old_hash=DEMO_HASH_OLD, new_hash=DEMO_HASH_NEW,
        summary=summary, diff_text=diff_text,
    )


class RunDemoUseCase:
    """Caso de uso do comando /preview — nunca lança exceção não tratada para
    o chamador (comando síncrono no webhook, mesmo padrão dos demais)."""

    def run(self) -> str:
        try:
            process = _get_or_create_demo_process()
            summary, diff_text = compute_diff(DEMO_OLD_TEXT, DEMO_NEW_TEXT)
            change = _get_or_create_demo_change(process, summary, diff_text)
            notification_excerpt = build_test_notification_body(
                process_label=process.label, process_url=process.effective_url, channel='telegram',
            )
            return messages.demo_preview(
                process=process,
                old_text=DEMO_OLD_TEXT,
                new_text=DEMO_NEW_TEXT,
                summary=change.summary,
                detected_at=timezone.now(),
                notification_excerpt=notification_excerpt,
            )
        except Exception:  # noqa: BLE001 — demonstração nunca pode travar o webhook
            return messages.demo_preview_error()
