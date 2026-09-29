# Implementation Plan: Precedentes — dossiê de due diligence (fundação)

**Branch**: `013-precedentes-due-diligence` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-precedentes-due-diligence/spec.md`

## Summary

Novo app de domínio `apps/precedentes/` com o modelo de dados fundacional de um caso de due
diligence (empresas, fatos com evidência e status, análises separadas dos fatos) e a disciplina de
revisão humana com histórico versionado ("fato ≠ análise, tudo com evidência anexada"),
implementada como schema Django (append-only por fato: corrigir nunca sobrescreve, sempre cria uma nova
versão). Sem IA (decisão confirmada com o dono do projeto) e sem nenhuma fonte externa nesta spec —
toda entrada é manual, via views autenticadas do painel. É a primeira de uma série de specs da
iniciativa "Precedentes"; pesquisa societária, jurisprudência, extração de documentos e relatório
final ficam para specs seguintes.

## Technical Context

**Language/Version**: Python 3.11 (Django 5.2.15).

**Primary Dependencies**: Django 5.2 apenas — nenhuma dependência nova (sem IA, sem scraping nesta
spec, Princípio VIII).

**Storage**: 4 modelos novos em `apps/precedentes/models.py` (`PrecedentCase`, `PrecedentEntity`,
`PrecedentFact`, `PrecedentAnalysis`) — ver data-model.md. `PrecedentFact` é a própria tabela de
versionamento (cada linha é uma versão; corrigir insere uma linha nova, nunca faz `UPDATE` do
valor), com o padrão `raiz_id`/`ativo` modelado como uma self-FK Django.

**Testing**: `django.test.TestCase`, sem nenhum mock de HTTP (não há chamada de rede nesta spec) —
os testes exercitam só o modelo de dados e as regras de negócio (services.py) diretamente.

**Target Platform**: Linux (Docker/Render), mesmo processo Gunicorn já existente — esta spec não
tem nenhum passo de `run_worker` (não há nada em segundo plano; tudo é CRUD síncrono via views).

**Project Type**: Web service (monolito Django) — novo app de domínio, só views + modelos.

**Performance Goals**: N/A — operações CRUD simples, sem volume que justifique otimização
específica nesta fase.

**Constraints**: Sem dependência nova (Princípio VIII); sem IA (decisão do dono do projeto); sem
fonte externa nova (logo, sem gate de cadência do Princípio II — primeira feature da iniciativa
Precedentes sem nenhum ponto de rede); autenticação obrigatória em toda view (Princípio geral do
painel).

**Scale/Scope**: Poucos casos de due diligence simultâneos, cada um com um punhado de empresas e
dezenas de fatos — nenhuma preocupação de escala nesta fase.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
|---|---|
| I. Simplicidade Operacional | **PASS** — sem processo/worker novo; nenhuma chamada de rede nesta spec (a primeira feature da iniciativa sem nenhum ponto de I/O externo). |
| II. Monitoramento Responsável | **N/A** — nenhuma fonte externa é consultada nesta spec. Pesquisa societária/jurisprudência (specs futuras da mesma iniciativa) tratarão seus próprios gates de cadência/constituição quando chegar a vez. |
| III. Django Monolítico Bem Organizado | **PASS** — novo app de domínio `apps/precedentes/` (`models.py`, `services.py`, `selectors.py`, `views.py`); escopo deliberadamente restrito à fundação, não ao epic inteiro (ver Complexity Tracking). |
| IV. PostgreSQL em Produção | **PASS** — 4 modelos novos, migrations portáveis Postgres/SQLite. |
| V. Notificações | **N/A** — esta spec não envia nenhuma notificação. |
| VI. Humanização das Mensagens | **PASS** — status de fato em português natural; fatos e análises com destaque visual distinto (FR-011), não JSON/IDs crus. |
| VII. Portfólio-Ready | **PASS** — testes cobrindo cada regra de negócio (FR-004 a FR-012), sem necessidade de fixture HTTP (não há rede nesta spec). |
| VIII. Sem Over-Engineering | **PASS** — sem IA, sem fonte externa, sem catálogo de campos pré-definido (campo é texto livre nesta versão), sem grafo societário automático — tudo isso fica para specs futuras só se/quando fizer sentido. |

## Project Structure

### Documentation (this feature)

```text
specs/013-precedentes-due-diligence/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/precedentes/
├── __init__.py
├── apps.py                  # PrecedentesConfig
├── models.py                  # PrecedentCase, PrecedentEntity, PrecedentFact, PrecedentAnalysis
├── admin.py
├── selectors.py                # casos do usuário, fatos atuais de uma empresa, histórico de um fato
├── services.py                # create_case, add_entity, remove_entity, record_fact, correct_fact,
│                              # record_analysis — cada regra de negócio (FR-004 a FR-012) mora aqui
├── views.py                    # CRUD autenticado: lista de casos, detalhe do caso, formulários
├── urls.py
├── migrations/
└── tests/
    ├── test_models.py
    ├── test_services.py
    └── test_views.py

templates/precedentes/
├── list.html                    # lista de casos
└── case_detail.html              # empresas + fatos + análises + histórico, formulários

config/settings.py                # +apps.precedentes no INSTALLED_APPS
config/urls.py                     # +include('apps.precedentes.urls')
```

**Structure Decision**: App de domínio novo e isolado (`apps/precedentes/`), como cada feature
anterior. Sem reaproveitamento de `apps/processes` (um "caso" de due diligence não é um
`MonitoredProcess` — pode existir sem nenhum processo SEI sendo acompanhado, spec.md Assumptions).
Sem `run_worker`/`services` de segundo plano nesta spec — é a primeira feature do projeto que é
puramente CRUD síncrono.

## Complexity Tracking

> Esta spec é deliberadamente a **primeira fatia** de uma iniciativa maior (16 tabelas, 8 etapas de
> pipeline no sistema original de referência). Cortar o escopo para só a fundação (modelo de dados + revisão/
> versionamento manual) é a decisão que mantém esta spec dentro do Princípio VIII — as specs
> seguintes (pesquisa societária, jurisprudência, extração de documentos, relatório final)
> assumirão sua própria carga de complexidade quando chegar a vez, cada uma com seu próprio
> Constitution Check.
