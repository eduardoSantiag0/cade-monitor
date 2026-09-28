"""
Montagem do pacote ZIP de documentos públicos de um processo (spec 012).
Ver specs/012-autos-processo-pacote/contracts/autos.md para o contrato completo.

Resumível entre chamadas: `monta_pacote` processa no máximo `max_documents` itens
por chamada (contracts/autos.md — um job grande não pode monopolizar um ciclo
inteiro do `run_worker`, que também precisa atender processos/notificações/dou/
agenda). O plano (quais documentos, com URL ou motivo já resolvidos) é montado
uma única vez, na primeira chamada, e persistido em `job.plan`.

Nunca lança exceção para o chamador — qualquer falha inesperada é capturada por
`services.run_pending_packages` e vira `status='failed'` no job.
"""
from __future__ import annotations

import os
import re
import time
import zipfile
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.monitoring.clients import (
    FetchError, NativeDocumentError, download_document, extract_document_links, get_snapshot,
)
from apps.monitoring.extractors import extract_movement_records, extract_protocol_records, folded

from .models import AutosPackageJob

_AUTOS_SUBDIR = 'autos_packages'
_CORROBORATION_KEYWORDS = ('restrit', 'sigilos', 'indispon', 'removid', 'exclu')


def _package_dir() -> str:
    path = os.path.join(settings.MEDIA_ROOT, _AUTOS_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def _building_path(job: AutosPackageJob) -> str:
    return os.path.join(_package_dir(), f'job_{job.pk}.zip.building')


def _final_path(job: AutosPackageJob) -> str:
    return os.path.join(_package_dir(), f'job_{job.pk}.zip')


def _safe_entry_name(text: str) -> str:
    cleaned = re.sub(r'[^\w.\- ]+', '_', (text or '').strip())
    return cleaned.strip('_ ') or 'documento'


def _corroboration_reason(record: dict, movements: list[dict]) -> str:
    """Motivo já declarado (andamento ou a própria Lista de Protocolos) para a
    ausência de link público de um documento — research.md, 'Placeholder de
    documento indisponível'. Vazio quando não há corroboração nenhuma."""
    doc_number = record.get('document', '')
    haystacks = [record.get('text', ''), record.get('doc_type', '')]
    for movement in movements:
        text = movement.get('text', '')
        if doc_number and doc_number in text:
            haystacks.append(text)
    for haystack in haystacks:
        if any(keyword in folded(haystack) for keyword in _CORROBORATION_KEYWORDS):
            return haystack.strip()
    return ''


def _fail(job: AutosPackageJob, message: str) -> None:
    building = _building_path(job)
    if os.path.exists(building):
        os.remove(building)
    job.status = AutosPackageJob.Status.FAILED
    job.error = message
    job.save(update_fields=['status', 'error', 'updated_at'])


def _build_plan(job: AutosPackageJob, timeout: int, user_agent: str) -> bool:
    """Primeira chamada de um job: busca a página fresca e monta o plano
    (um item por documento declarado, com URL e/ou motivo já resolvidos).
    Retorna False (e já marca o job como failed) se o fetch inicial falhar."""
    try:
        snapshot = get_snapshot(job.process.effective_url, timeout, user_agent)
    except FetchError as exc:
        _fail(job, f'Falha ao acessar a página do processo: {exc}')
        return False

    records = extract_protocol_records(snapshot.text)
    links = extract_document_links(snapshot.html, snapshot.url)
    movements = extract_movement_records(snapshot.text)

    plan = []
    for idx, record in enumerate(records, start=1):
        doc_number = record.get('document', '')
        plan.append({
            'idx': idx,
            'document': doc_number,
            'label': _safe_entry_name(record.get('doc_type') or doc_number),
            'url': links.get(doc_number, ''),
            'motivo': _corroboration_reason(record, movements),
            'record': record,
        })

    job.total_declared = len(plan)
    job.total_processed = 0
    job.plan = plan
    job.next_index = 0
    job.divergences = []
    job.save(update_fields=[
        'total_declared', 'total_processed', 'plan', 'next_index', 'divergences', 'updated_at',
    ])
    return True


def _process_item(zf: zipfile.ZipFile, item: dict, timeout: int, user_agent: str) -> str | None:
    """Escreve a entrada correspondente no ZIP (real ou placeholder). Retorna o
    número do documento quando é uma divergência (nada escrito), ou None."""
    idx = item['idx']
    written = False

    if item['url']:
        try:
            attachment = download_document(item['url'], item['record'], timeout, user_agent)
            filename = attachment.get('filename') or f"{item['label']}.bin"
            zf.writestr(f'{idx}. {filename}', attachment['content'])
            written = True
        except NativeDocumentError:
            pass
        except FetchError:
            pass
        finally:
            if settings.SLEEP_BETWEEN_REQUESTS_SECONDS > 0:
                time.sleep(settings.SLEEP_BETWEEN_REQUESTS_SECONDS)

    if written:
        return None

    if item['motivo']:
        zf.writestr(f"{idx}. {item['label']}.txt", item['motivo'])
        return None

    return item['document'] or f"posição {idx}"


def monta_pacote(job: AutosPackageJob, timeout: int, user_agent: str, max_documents: int = 1) -> None:
    """Avança o job em até `max_documents` itens do plano nesta chamada. Nunca
    lança exceção para o chamador."""
    if job.total_declared is None:
        if not _build_plan(job, timeout, user_agent):
            return

    plan = job.plan
    building_path = _building_path(job)
    mode = 'a' if os.path.exists(building_path) else 'w'
    processed_this_call = 0

    try:
        with zipfile.ZipFile(building_path, mode, zipfile.ZIP_DEFLATED) as zf:
            while job.next_index < len(plan) and processed_this_call < max_documents:
                divergent_document = _process_item(zf, plan[job.next_index], timeout, user_agent)
                if divergent_document:
                    job.divergences = [*job.divergences, divergent_document]
                job.next_index += 1
                job.total_processed = job.next_index
                processed_this_call += 1
    except Exception:
        if os.path.exists(building_path):
            os.remove(building_path)
        raise

    job.save(update_fields=['next_index', 'total_processed', 'divergences', 'updated_at'])

    if job.next_index < len(plan):
        return  # ainda há itens — próxima chamada continua

    if job.divergences:
        os.remove(building_path)
        job.status = AutosPackageJob.Status.FAILED
        job.error = (
            f'{len(job.divergences)} documento(s) sem link público e sem motivo declarado: '
            f'{", ".join(job.divergences)}.'
        )
        job.save(update_fields=['status', 'error', 'updated_at'])
        return

    final_path = _final_path(job)
    os.replace(building_path, final_path)
    job.file_path = os.path.join(_AUTOS_SUBDIR, os.path.basename(final_path))
    job.status = AutosPackageJob.Status.READY
    job.expires_at = timezone.now() + timedelta(seconds=settings.AUTOS_PACKAGE_TTL_SECONDS)
    job.save(update_fields=['file_path', 'status', 'expires_at', 'updated_at'])
