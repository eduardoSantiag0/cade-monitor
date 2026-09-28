# Implementation Plan: Digest diário do DOU

**Branch**: `009-digest-diario-dou` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-digest-diario-dou/spec.md`

## Summary

Novo app de domínio `apps/dou/` que busca, uma vez por dia dentro de janelas configuráveis, as
publicações do CADE saídas no Diário Oficial da União (fonte primária: Resenha do CADE em
`sinc.cade.gov.br`; fallback: listagem pública do DOU em `www.in.gov.br/leiturajornal`), monta um
e-mail em português com formatação de negrito/destaque por termo monitorado, e o envia via o canal
de e-mail já existente (`apps/notifications/channels/email.py`). Duas rotinas adicionais e
opcionais por assinante — antecipação da véspera a partir do boletim do SEI e confirmação da
manhã seguinte — reaproveitam o mesmo motor de formatação e a mesma infraestrutura de busca. Tudo
roda dentro do laço já existente de `run_worker` (`apps/monitoring/management/commands/
run_worker.py:_run_cycle`), sem processo/worker novo, respeitando a cadência mínima de 5 minutos
entre tentativas à mesma fonte definida pela emenda do Princípio II (v2.2.0).

## Technical Context

**Language/Version**: Python 3.11 (Django 5.2.15) — mesma stack do restante do projeto.

**Primary Dependencies**: Django 5.2, `urllib` da stdlib para HTTP (mesmo padrão de
`apps/monitoring/clients.py`), `django.core.mail` via o canal já existente. Nenhuma dependência
nova — leitura de PDF (`pypdf`) e impressão de PDF via navegador headless ficam fora de escopo
(spec.md, Assumptions).

**Storage**: PostgreSQL em produção / SQLite em dev-teste (padrão do projeto). Cinco modelos
novos, todos no app `dou` (ver data-model.md); nenhuma mudança em modelos existentes.

**Testing**: `django.test.TestCase`, fixtures HTML/JSON locais para a Resenha e para a listagem do
in.gov.br (sem HTTP real nos testes automatizados), `unittest.mock.patch` para o envio de e-mail e
para o relógio (janelas diárias). Validação ao vivo (1-2 chamadas reais) das duas fontes externas
durante a implementação, documentada em research.md.

**Target Platform**: Linux (Docker/Render), mesmo processo Gunicorn + worker único já existente.

**Project Type**: Web service (monolito Django) — novo app de domínio, sem novo processo/serviço.

**Performance Goals**: Busca no máximo 1x a cada 5 minutos por fonte, dentro de janelas diárias
limitadas (não polling contínuo); o custo por tick do worker quando fora de qualquer janela é O(1)
(uma leitura de estado, sem HTTP). Envio de e-mail é O(assinantes ativos) por tipo de envio, uma
vez por dia.

**Constraints**: Sem dependência de runtime nova (Princípio VIII); sem requisições paralelas às
fontes do DOU (Princípio II); deve caber no orçamento de 1–2 vCPU / ≤ 512 MB (Princípio I); nenhum
processo/worker/cron adicional — tudo dentro do `run_worker` já existente (Princípio I, não usar o
container `scheduler` do docker-compose, cujo laço `sleep 86400` não serve para horário de parede).

**Scale/Scope**: Dezenas de assinantes do digest (mesma ordem de grandeza dos assinantes de
processo já existentes); um documento diário por fonte, não escala com número de processos
monitorados.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
|---|---|
| I. Simplicidade Operacional | **PASS** — sem processo/worker/serviço novo; busca e envio entram no `run_worker` existente, gated por janela + marcador de última tentativa (não polling contínuo); stdlib `urllib` para HTTP. |
| II. Monitoramento Responsável | **PASS** — coberto pela emenda v2.2.0: fontes `in.gov.br`/`sinc.cade.gov.br` já em escopo, com cadência própria (≥5 min entre tentativas, janela diária, sem burst) que este plano implementa via o marcador de última tentativa por fonte. |
| III. Django Monolítico Bem Organizado | **PASS** — novo app de domínio `apps/dou/` (`models.py`, `services.py`, `selectors.py`, `admin.py`), seguindo o padrão dos apps existentes; views não fazem lógica de negócio. |
| IV. PostgreSQL em Produção | **PASS** — migrations portáveis Postgres/SQLite, sem SQL específico de vendor. |
| V. Notificações | **PASS** — reaproveita `apps/notifications/channels/email.py` sem alterar sua interface; não adiciona Telegram/WhatsApp para o DOU (fora de escopo confirmado). |
| VI. Humanização das Mensagens | **PASS** — e-mails em português natural, com negrito/destaque legível por não técnicos (FR-006, SC-004); dias sem publicação recebem aviso explícito, nunca silêncio (FR-005, FR-011). |
| VII. Portfólio-Ready | **PASS** — testes com fixtures locais para os dois parsers de fonte, `--help` nos management commands se algum for criado, logs estruturados nas tentativas de busca e envio (FR-013). |
| VIII. Sem Over-Engineering | **PASS** — sem dependência nova; modelos de estado deliberadamente mínimos (um `DouFetchState` genérico por fonte, um campo JSON para o "antecipado da véspera" em vez de tabelas extras) — ver data-model.md e research.md para as alternativas descartadas. |

## Project Structure

### Documentation (this feature)

```text
specs/009-digest-diario-dou/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md         # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/dou/
├── __init__.py
├── apps.py                  # DouConfig
├── models.py                 # DouSubscription, DouMonitoredTerm, DouSendLog, DouFetchState,
│                              # DouAnticipation (ver data-model.md)
├── admin.py                  # Registro simples para cadastro manual (sem UI dedicada nesta versão)
├── clients.py                 # fetch_resenha(date), fetch_ingov_listing(date) — HTTP stdlib,
│                              # mesmo padrão de apps/monitoring/clients.py
├── parsers.py                 # Resenha HTML → dict; listagem in.gov.br → dict; filtro por CADE
├── render.py                  # Formatação do e-mail: negrito de título/partes, truncamento de
│                              # despacho longo, destaque por termo monitorado (texto e HTML)
├── selectors.py                # Queries: assinantes ativos, termos monitorados por assinante,
│                              # já-enviado-hoje?
├── services.py                # Orquestração: run_digest_window(), run_anticipation_window(),
│                              # run_confirmation_window() — chamadas pelo run_worker
├── migrations/
└── tests/
    ├── fixtures/               # HTML/JSON de exemplo da Resenha e da listagem in.gov.br
    ├── test_parsers.py
    ├── test_render.py
    ├── test_services.py
    └── test_clients.py         # validação ao vivo opcional, marcada e não roda no CI padrão

apps/monitoring/management/commands/run_worker.py   # +3 chamadas gated por janela em _run_cycle
config/settings.py                                    # +apps.dou no INSTALLED_APPS, +env DOU_*
config/env_schema.py                                  # janelas/horários configuráveis
```

**Structure Decision**: App de domínio novo e isolado (`apps/dou/`) em vez de estender
`apps/monitoring/` — mantém o scraping de processo (SEI, por processo monitorado) separado da
busca de fonte diária única (DOU), que tem modelo de dados, cadência e ciclo de vida próprios.
Reaproveita `apps/notifications/channels/email.py` e `apps/subscribers/Subscriber.is_reachable()`
por composição (import direto de função), sem depender das partes de `apps/monitoring` que são
específicas de processo (extractors, diff de andamentos).

## Complexity Tracking

*Nenhuma violação da constituição a justificar — todos os gates acima são PASS.*
