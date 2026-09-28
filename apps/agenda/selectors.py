"""Queries reutilizáveis do app agenda. Lógica de negócio fica em services.py/deadlines.py."""
from __future__ import annotations

from . import deadlines


def timeline_for_process(process) -> list[dict] | None:
    """Wrapper fino sobre `deadlines.monta_linha_do_tempo`, para a view não
    importar direto de dentro do app. `None` quando o processo não é AC sumário
    (a view não renderiza a seção)."""
    if deadlines.classifica_processo(process.last_text) != 'ac_sumario':
        return None
    return deadlines.monta_linha_do_tempo(process)
