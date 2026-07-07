"""
Lógica de comparação de snapshots e geração de diff humanizado.

Estratégia de dois níveis:
  1. Diff estruturado CADE/SEI: detecta novos andamentos e protocolos com precisão.
     Gera resumos como "2 novos andamentos detectados."
  2. Diff genérico por linhas: fallback para páginas sem estrutura CADE reconhecível.
     Mostra linhas adicionadas e removidas.

Separado de extractors.py para facilitar testes isolados.
"""
from __future__ import annotations

from .extractors import extract_cade_entries


def compute_diff(old_text: str | None, new_text: str, max_lines: int = 12) -> tuple[str, str]:
    """
    Compara dois textos e retorna (resumo, diff_detalhado).
    Tenta primeiro o diff estruturado CADE/SEI; usa diff genérico como fallback.
    """
    structured = _structured_cade_diff(old_text, new_text, max_lines)
    if structured:
        return structured

    return _generic_line_diff(old_text, new_text, max_lines)


def _structured_cade_diff(
    old_text: str | None,
    new_text: str,
    max_items: int = 12,
) -> tuple[str, str] | None:
    """
    Diff estruturado: compara andamentos e protocolos usando a extração semântica.
    Retorna None se não encontrar entradas estruturadas reconhecíveis.
    """
    old_entries = extract_cade_entries(old_text or '')
    new_entries = extract_cade_entries(new_text)

    old_protocols = set(old_entries['protocols'])
    old_movements = set(old_entries['movements'])
    added_movements = [e for e in new_entries['movements'] if e not in old_movements]
    added_protocols = [e for e in new_entries['protocols'] if e not in old_protocols]

    if not added_movements and not added_protocols:
        return None

    summary_parts: list[str] = []
    detail_lines: list[str] = []

    if added_movements:
        summary_parts.append(f'{len(added_movements)} novo(s) andamento(s) detectado(s).')
        detail_lines.append('Andamentos novos:')
        detail_lines.extend(added_movements[:max_items])

    if added_protocols:
        summary_parts.append(f'{len(added_protocols)} novo(s) documento(s)/protocolo(s) detectado(s).')
        if detail_lines:
            detail_lines.append('')
        detail_lines.append('Documentos/protocolos novos:')
        detail_lines.extend(added_protocols[:max_items])

    hidden = (
        max(0, len(added_movements) - max_items)
        + max(0, len(added_protocols) - max_items)
    )
    if hidden:
        detail_lines.append(f'... mais {hidden} registro(s) novo(s).')

    # O resumo inclui as primeiras linhas dos registros novos para o e-mail/WhatsApp
    highlighted = (added_movements + added_protocols)[:max_items]
    summary = '\n'.join(summary_parts + highlighted)
    return summary[:4000], '\n'.join(detail_lines)[:8000]


def _generic_line_diff(
    old_text: str | None,
    new_text: str,
    max_lines: int = 12,
) -> tuple[str, str]:
    """
    Diff genérico baseado em conjuntos de linhas.
    Funciona para qualquer tipo de página, não só CADE/SEI.
    """
    old_lines = [line for line in (old_text or '').splitlines() if line.strip()]
    new_lines = [line for line in new_text.splitlines() if line.strip()]
    old_set = set(old_lines)
    new_set = set(new_lines)

    added = [line for line in new_lines if line not in old_set]
    removed = [line for line in old_lines if line not in new_set]

    if added:
        summary = 'Novas linhas detectadas:\n' + '\n'.join(added[:max_lines])
        if len(added) > max_lines:
            summary += f'\n... mais {len(added) - max_lines} linha(s).'
    else:
        summary = 'A página mudou, mas não foram identificadas linhas novas isoladas.'

    diff_lines: list[str] = []
    if added:
        diff_lines.append('Adicionado:')
        diff_lines.extend(f'+ {line}' for line in added[:max_lines])
    if removed:
        if diff_lines:
            diff_lines.append('')
        diff_lines.append('Removido:')
        diff_lines.extend(f'- {line}' for line in removed[:max_lines])
    if not diff_lines:
        diff_lines.append(summary)

    return summary[:4000], '\n'.join(diff_lines)[:8000]
