# Implementation Plan: Agenda e prazos de AC sumário

**Branch**: `011-agenda-prazos-ac` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-agenda-prazos-ac/spec.md`

## Summary

Novo app de domínio `apps/agenda/` que: (1) mantém um calendário de dias úteis do CADE por ano,
sincronizado em segundo plano a partir do ato oficial (Portaria) publicado no DOU via a mesma
listagem já usada pela feature 009 (`in.gov.br`, já em escopo constitucional); (2) calcula, para
processos elegíveis (Ato de Concentração Sumário), uma linha do tempo de prazos a partir dos
documentos já extraídos por `apps/monitoring/extractors.py::extract_protocol_records`; (3) gera e
envia convites de calendário (`.ics`, stdlib puro) para os dois prazos "do escritório"; (4) apaga
processos elegíveis 10 dias após o trânsito em julgado sem nova movimentação, com quatro guardas
de segurança explícitas (ação irreversível, confirmada com o dono do projeto). Tudo entra no
`run_worker` já existente, sem processo novo.

## Technical Context

**Language/Version**: Python 3.11 (Django 5.2.15).

**Primary Dependencies**: Django 5.2; stdlib `urllib` para HTTP (mesmo padrão de
`apps/dou/clients.py`/`apps/monitoring/clients.py`); geração de `.ics` por template de texto
stdlib (sem `icalendar` nem lib de terceiro — Princípio VIII).

**Storage**: 3 modelos novos em `apps/agenda/models.py` (`CadeCalendarYear`,
`CadeCalendarEntry`, `ProcessInvite`) — ver data-model.md. A linha do tempo de prazos em si NUNCA
é persistida (recalculada a cada leitura, a partir dos documentos + calendário atuais) — só o que
já foi *enviado* como convite precisa de estado (`ProcessInvite`), para
decidir reenviar/atualizar/cancelar.

**Testing**: `django.test.TestCase`, fixtures de texto simulando `MonitoredProcess.last_text`
(documentos de um AC sumário em diferentes estágios) e calendário oficial fixo; `unittest.mock`
para HTTP, envio de e-mail e o relógio; a suíte de FR-017/FR-018 (auto-encerramento) cobre cada
guarda de segurança isoladamente (Princípio VII).

**Target Platform**: Linux (Docker/Render), mesmo processo Gunicorn + worker único já existente.

**Project Type**: Web service (monolito Django) — novo app de domínio, sem processo/serviço novo.

**Performance Goals**: Sincronização do calendário no máximo 1x/dia (janela intensiva) ou
1x/30 dias (confirmado); cálculo de linha do tempo e verificação de auto-encerramento rodam por
processo elegível a cada ciclo do worker, custo O(nº de processos AC sumário ativos), mesma ordem
de grandeza do que `get_due_processes` já processa hoje.

**Constraints**: Sem dependência nova (Princípio VIII); sem processo/worker novo (Princípio I);
fonte do calendário (`in.gov.br`) já em escopo constitucional (emenda v2.2.0) — nenhuma nova
emenda necessária nesta feature (camada de comunicados avulsos do CADE, domínio ainda não
avaliado, fica fora de escopo — spec.md, Assumptions); auto-encerramento é ação destrutiva
irreversível, confirmada explicitamente com o dono do projeto, e MUST manter as quatro guardas de
segurança de FR-017/FR-018 sem exceção.

**Scale/Scope**: Escala com o nº de processos monitorados classificados como AC sumário — mesma
ordem de grandeza dos processos já monitorados hoje (dezenas), não com o volume total do DOU.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
|---|---|
| I. Simplicidade Operacional | **PASS** — sem processo/worker novo; sincronização do calendário e cálculo de prazos entram no `run_worker` existente, gated por cadência (calendário) e por processo elegível (prazos). |
| II. Monitoramento Responsável | **PASS** — fonte do calendário oficial (`in.gov.br`) já em escopo (emenda v2.2.0, feature 009); cadência diária/30-dias é mais frugal que a cadência mínima de 5 min já exigida para o DOU. A camada de comunicados avulsos do CADE (domínio distinto, ainda não avaliado) fica explicitamente fora de escopo — ver Assumptions. |
| III. Django Monolítico Bem Organizado | **PASS** — novo app de domínio `apps/agenda/` (`models.py`, `services.py`, `selectors.py`, `calendar_source.py`, `deadlines.py`, `ics.py`, `admin.py`); reaproveita `extract_protocol_records` (monitoring) e `ProcessSubscription` (subscribers) por composição, sem duplicar. |
| IV. PostgreSQL em Produção | **PASS** — 3 modelos novos, migrations portáveis Postgres/SQLite. |
| V. Notificações | **PASS** — convite de calendário é um anexo `.ics` no e-mail já existente (`apps/notifications/channels/email.py`), reaproveitando o mesmo `html=`/anexo já suportado; nenhum canal novo. |
| VI. Humanização das Mensagens | **PASS** — corpo do e-mail do convite em português natural; linha do tempo exibida na página do processo já existente, com rótulos humanos (não JSON cru). |
| VII. Portfólio-Ready | **PASS** — testes cobrindo cada fórmula de prazo (FR-004/007-010), cada guarda de segurança do auto-encerramento isoladamente (FR-017/018), e o parser do ato oficial com fixture local. |
| VIII. Sem Over-Engineering | **PASS** — geração de `.ics` por template de texto (stdlib pura, sem lib nova); linha do tempo nunca persistida (evita um histórico que ninguém pediu); auto-encerramento reaproveita campos já existentes de `MonitoredProcess` (`last_checked_at`, `last_error`) em vez de duplicar estado. |

## Project Structure

### Documentation (this feature)

```text
specs/011-agenda-prazos-ac/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/agenda/
├── __init__.py
├── apps.py                    # AgendaConfig
├── models.py                   # CadeCalendarYear, CadeCalendarEntry, ProcessInvite
├── admin.py
├── calendar_source.py           # busca/parsing/validação do ato oficial (in.gov.br) + sync
├── deadlines.py                 # classificação do processo, matching de documentos, fórmula
│                                # de prazo (calcula_prazo_cade), montagem da linha do tempo
├── ics.py                       # geração de .ics (texto puro, RFC 5545 mínimo)
├── selectors.py                  # processos AC sumário elegíveis, convites já enviados
├── services.py                  # orquestração: sync_calendar(), refresh_timelines_and_invites(),
│                                # run_auto_closure() — chamadas pelo run_worker
├── migrations/
└── tests/
    ├── fixtures/                 # texto de processo em cada estágio, ato oficial de exemplo
    ├── test_calendar_source.py
    ├── test_deadlines.py
    ├── test_ics.py
    └── test_services.py          # inclui os testes isolados de cada guarda do auto-encerramento

apps/monitoring/management/commands/run_worker.py   # +3 chamadas gated em _run_cycle
apps/notifications/channels/email.py                  # já suporta anexo — sem mudança
templates/processes/detail.html                        # +seção da linha do tempo (condicional)
config/settings.py                                      # +apps.agenda, +env AGENDA_*
config/env_schema.py                                    # cadência/janelas configuráveis
```

**Structure Decision**: App de domínio novo (`apps/agenda/`), pelo mesmo racional da feature 009
(módulos de negócio próprios — classificação de processo, fórmula de prazo, geração de `.ics` —
não pertencem a `apps/monitoring`, que é scraping/extração genérica). Diferente da feature 009,
reaproveita `ProcessSubscription` diretamente (sem inscrição própria), porque prazos são por
processo, não uma lista global como o digest do DOU.

## Complexity Tracking

> Auto-encerramento (FR-017/018) é uma ação destrutiva/irreversível — não é uma violação de
> princípio da constituição, mas é o único ponto desta feature que exige cuidado redobrado de
> implementação e teste (ver research.md e tasks.md). Registrado aqui para visibilidade, não como
> gate de constituição.
