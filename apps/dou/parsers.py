"""
Parsers das fontes externas do digest DOU: Resenha do CADE (HTML embutido na resposta
Solr) e listagem pública do in.gov.br. Produzem o mesmo formato normalizado
`{'editais': [...], 'despachos': [...], 'atas': [...]}` (cada item:
`{'titulo': str, 'text': str, 'url': str}`), consumido por `render.py` independentemente
de qual fonte respondeu (contracts/dou-services.md).

Formato validado ao vivo (spec 009, tasks.md T053) contra as duas fontes reais em
2026-09-28 — ver "Correção pós-implementação" em research.md para o que a validação
mudou em relação ao design original.
"""
from __future__ import annotations

import html as html_lib
import json
import re

from .clients import is_cade_item
from .render import _CASE_TITLE_RE, fold

_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')


def _strip_tags(fragment: str) -> str:
    return html_lib.unescape(_WS_RE.sub(' ', _TAG_RE.sub(' ', fragment or ''))).strip()


def _split_items_by_case_title(text: str) -> list[dict[str, str]]:
    """Um bloco de texto pode conter vários itens; cada um começa numa citação de
    título de caso (Ato de Concentração, Processo Administrativo etc.). Sem nenhuma
    citação reconhecida, devolve o texto inteiro como um item genérico (nunca some
    conteúdo em silêncio)."""
    text = _strip_tags(text)
    if not text:
        return []
    starts = [m.start() for m in _CASE_TITLE_RE.finditer(text)]
    if not starts:
        return [{'titulo': '', 'text': text, 'url': ''}]
    starts.append(len(text))
    items = []
    for start, end in zip(starts, starts[1:]):
        piece = text[start:end].strip()
        if piece:
            title_match = _CASE_TITLE_RE.search(piece)
            items.append({'titulo': title_match.group(0) if title_match else '', 'text': piece, 'url': ''})
    return items


def _dedupe_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """Deduplicação intra-fonte (FR-016): mesmo texto normalizado nunca aparece 2x."""
    seen: set[str] = set()
    out = []
    for item in items:
        key = fold(item.get('text', ''))
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def parse_sei_publications(html: str) -> list[dict]:
    """Publicações do SEI (boletim) para a antecipação da véspera (User Story 2) — lista
    plana de andamentos, sem distinção edital/despacho (a página de publicações do SEI
    não separa os dois da mesma forma que a Resenha). Ver research.md, "Correção
    pós-implementação", para o achado de que `fetch_sei_publications` ainda não retorna
    uma página de resultados de verdade (a busca é disparada por JS/AJAX, não por um
    POST direto de formulário) — o HTML real hoje volta é a casca da página de busca,
    sem nenhuma citação de caso.

    Por isso, ao contrário de `_split_items_by_case_title` puro (usado para a Resenha,
    onde o texto já filtrado por CADE é sempre conteúdo real), aqui NÃO caímos no
    fallback de "nenhuma citação reconhecida -> devolve o texto inteiro como um item":
    sobre a casca da página (JS/CSS/menu, sem nenhum título de caso), isso mandaria
    lixo como se fosse uma publicação real. Preferimos "sem itens" (que já vira o aviso
    correto de "sem publicações previstas") a inventar um item.
    ponytail: heurística conservadora enquanto `fetch_sei_publications` não retorna
    resultados reais — reavaliar assim que o endpoint de busca for corrigido."""
    items = _split_items_by_case_title(html)
    if len(items) == 1 and not items[0]['titulo']:
        return []
    return _dedupe_items(items)


# ---------------------------------------------------------------------------
# Resenha do CADE (sinc.cade.gov.br)
# ---------------------------------------------------------------------------
#
# Formato real (validado ao vivo): um único documento HTML com <div>s sequenciais,
# cada um opcionalmente todo em <strong>. Não há cabeçalhos "Editais"/"Despachos"/
# "Atas" — a estrutura real é: "Seção N" (bold) -> nome do órgão (bold, logo em
# seguida) -> um <strong> de título por item ("DESPACHO Nº 44, DE ...") seguido de
# um ou mais <div>s de corpo em texto normal, até o próximo título ou até a próxima
# seção/órgão. Um mesmo dia cita órgãos variados (CADE não é o único); só o texto sob
# o cabeçalho de órgão do CADE entra no digest.

_DIV_RE = re.compile(r'<div[^>]*>(.*?)</div>', re.I | re.S)
_STRONG_ONLY_RE = re.compile(r'\A<strong>(.*)</strong>\Z', re.I | re.S)
_SECAO_RE = re.compile(r'^se[çc][ãa]o\s+\d+$', re.I)


def _resenha_blocks(html: str) -> list[tuple[bool, str]]:
    """Lista (é_negrito, texto_puro) de cada <div> do documento, na ordem."""
    blocks = []
    for raw in _DIV_RE.findall(html or ''):
        stripped = raw.strip()
        bold_match = _STRONG_ONLY_RE.match(stripped)
        text = _strip_tags(bold_match.group(1) if bold_match else raw)
        if text:
            blocks.append((bool(bold_match), text))
    return blocks


def _cade_text_by_secao(html: str) -> dict[int, str]:
    """Concatena o texto (títulos inclusive) de todo bloco pertencente à seção/órgão
    CADE, indexado pelo número da seção do DOU (1, 2, 3...)."""
    by_secao: dict[int, list[str]] = {}
    current_secao: int | None = None
    in_cade = False
    expect_orgao = False
    for is_bold, text in _resenha_blocks(html):
        if is_bold and _SECAO_RE.match(text):
            current_secao = int(re.search(r'\d+', text).group())
            in_cade = False
            expect_orgao = True
            continue
        if expect_orgao and is_bold:
            in_cade = is_cade_item(text)
            expect_orgao = False
            continue
        if in_cade and current_secao is not None:
            by_secao.setdefault(current_secao, []).append(text)
    return {secao: ' '.join(parts) for secao, parts in by_secao.items()}


def parse_resenha_html(html: str) -> dict:
    by_secao = _cade_text_by_secao(html)
    # Seção 1: despachos/decisões do CADE. Seção 3: editais/avisos/extratos.
    # Atas/pautas de sessão: nenhum exemplo real apareceu no dia validado ao vivo
    # (tasks.md T053) — sem um exemplo real para calibrar a extração, `atas` fica
    # vazia por ora em vez de uma heurística especulativa (research.md). O rodapé de
    # `render.py` já funciona normalmente assim que `atas` vier populada por alguma
    # fonte (é só uma lista de {'titulo','url'} — ver `render.render_digest_html`).
    despachos_raw = _split_items_by_case_title(by_secao.get(1, '')) if by_secao.get(1) else []
    editais_raw = _split_items_by_case_title(by_secao.get(3, '')) if by_secao.get(3) else []
    return {
        'editais': _dedupe_items(editais_raw),
        'despachos': _dedupe_items(despachos_raw),
        'atas': [],
    }


# ---------------------------------------------------------------------------
# Listagem in.gov.br (fallback) — validada ao vivo: os itens do dia vêm embutidos
# como JSON num <script id="params" type="application/json">, não como HTML com
# classes CSS previsíveis (a página é majoritariamente renderizada em JS). O
# `content` de cada item é um RESUMO curto (~400 caracteres), não o texto integral —
# abrir o artigo completo por `urlTitle` fica fora de escopo do v1 (research.md).
# ---------------------------------------------------------------------------

_PARAMS_SCRIPT_RE = re.compile(
    r'<script[^>]*id="params"[^>]*>(.*?)</script>', re.I | re.S,
)
_INGOV_ARTICLE_BASE = 'https://www.in.gov.br/web/dou/-/'


def _extract_json_array(html: str) -> list[dict]:
    match = _PARAMS_SCRIPT_RE.search(html or '')
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return data.get('jsonArray') or []


def parse_ingov_listing(htmls: list[str]) -> dict:
    """Filtra a listagem in.gov.br (seções 1 e 3) para itens do CADE e normaliza para
    o mesmo formato de `parse_resenha_html`, classificando por `artType` (Edital vs.
    demais tipos, tratados como despacho)."""
    editais: list[dict[str, str]] = []
    despachos: list[dict[str, str]] = []
    for html in htmls:
        for entry in _extract_json_array(html):
            hierarchy = entry.get('hierarchyStr', '')
            if not is_cade_item(hierarchy):
                continue
            titulo = html_lib.unescape(entry.get('title') or '')
            text = html_lib.unescape(entry.get('content') or '')
            url_title = entry.get('urlTitle') or ''
            item = {
                'titulo': titulo,
                'text': text or titulo,
                'url': f'{_INGOV_ARTICLE_BASE}{url_title}' if url_title else '',
            }
            if fold(entry.get('artType', '')) == 'edital':
                editais.append(item)
            else:
                despachos.append(item)
    return {
        'editais': _dedupe_items(editais),
        'despachos': _dedupe_items(despachos),
        'atas': [],
    }
