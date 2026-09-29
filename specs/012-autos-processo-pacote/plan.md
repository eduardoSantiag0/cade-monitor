# Implementation Plan: Pacote de autos (documentos públicos) do processo

**Branch**: `012-autos-processo-pacote` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-autos-processo-pacote/spec.md`

## Summary

Novo app de domínio `apps/autos/` que monta, em segundo plano via `run_worker`, um ZIP com todos
os documentos públicos de um processo monitorado, numerados na ordem da Lista de Protocolos.
Reaproveita `apps/monitoring/clients.py::get_snapshot` (fetch fresco da página, nunca o texto já
normalizado guardado — nunca confiar num snapshot potencialmente
desatualizado), `extract_document_links`/`extract_protocol_records` (extração já existente) e
`download_document` (download de um documento, já com limite de tamanho configurado) para cada
documento. Documento sem link público vira um placeholder `.txt` só quando o andamento/página já
extraída explica o motivo; sem essa corroboração, conta como divergência e o job inteiro falha
(nunca entrega ZIP parcial). Sem sessão autenticada no SEI, sem pasta Confidencial/, sem
`autos_vigia` — fora de escopo (spec.md, Assumptions).

## Technical Context

**Language/Version**: Python 3.11 (Django 5.2.15).

**Primary Dependencies**: Django 5.2; `zipfile`/`urllib` da stdlib (sem dependência nova — não há
merge de PDF nem impressão HTML→PDF nesta versão, Princípio VIII).

**Storage**: 1 modelo novo (`AutosPackageJob`) em `apps/autos/models.py` — status, timestamps,
caminho do arquivo pronto, erro. O ZIP em si fica em disco (`MEDIA_ROOT`), não como blob em banco
(spec.md, Assumptions) — mesmo racional de "SEI é a fonte de verdade sempre disponível" já usado
pela feature 011 para não persistir a linha do tempo de prazos.

**Testing**: `django.test.TestCase`, fixtures de HTML/texto de processo (Lista de Protocolos com
documentos com/sem link, um documento ZIP), `unittest.mock` para HTTP e para o relógio/clock do
job. Teste de integridade força uma divergência declarada×processada (FR-009) e confirma que
nenhum arquivo fica disponível.

**Target Platform**: Linux (Docker/Render), mesmo processo Gunicorn + worker único já existente.

**Project Type**: Web service (monolito Django) — novo app de domínio + 1 view de pedido/status/
download na página do processo já existente.

**Performance Goals**: Um job por vez por processo (FR-005); pausa configurável
(`SLEEP_BETWEEN_REQUESTS_SECONDS`, já existente) entre cada download dentro do job — processos de
centenas de documentos levam minutos, não segundos, e isso é aceitável porque roda em segundo
plano, nunca bloqueando o Gunicorn.

**Constraints**: Sem dependência nova (Princípio VIII); ZIP montado e escrito em streaming para
disco, nunca inteiro em memória de uma vez (Princípio I, ≤512MB RAM); nenhuma sessão autenticada
no SEI (Princípio II atual, sem emenda nesta feature — spec.md, Assumptions); reaproveita
`download_document`/`DOCUMENT_DOWNLOAD_MAX_BYTES` já existentes, sem reimplementar o download.

**Scale/Scope**: Escala com o número de documentos do processo pedido (dezenas a centenas), não
com o número total de processos monitorados — só processa quando alguém pede.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
|---|---|
| I. Simplicidade Operacional | **PASS** — sem processo/worker novo; a montagem roda como um passo gated do `run_worker` existente (um job por vez, não polling contínuo custoso); ZIP escrito em streaming para disco, nunca acumulado inteiro em memória. |
| II. Monitoramento Responsável | **PASS** — GET público sem autenticação, mesmo padrão de scraping já usado; pausa configurável entre downloads dentro do job evita rajada (reaproveita `SLEEP_BETWEEN_REQUESTS_SECONDS`). Sem sessão autenticada no SEI (a metade que exigiria isso fica fora de escopo — spec.md, Assumptions). |
| III. Django Monolítico Bem Organizado | **PASS** — novo app de domínio `apps/autos/` (`models.py`, `services.py`, `selectors.py`, `views.py`); reaproveita `apps/monitoring/clients.py` por composição, sem duplicar download/extração. |
| IV. PostgreSQL em Produção | **PASS** — 1 modelo novo, migration portável; nenhum blob binário no banco (arquivo fica em disco). |
| V. Notificações | **N/A** — esta feature não envia notificação; é download sob demanda pela própria página do processo. |
| VI. Humanização das Mensagens | **PASS** — status do job (fila/processando/pronto/falhou) e mensagem de erro em português, legível por não técnicos. |
| VII. Portfólio-Ready | **PASS** — testes cobrindo o caminho feliz, placeholder de documento indisponível, e a checagem de integridade (divergência declarado×processado), com fixtures locais (sem HTTP real). |
| VIII. Sem Over-Engineering | **PASS** — sem merge de PDF, sem impressão HTML→PDF, sem expansão recursiva de ZIP aninhado, sem persistência de blob — todas simplificações deliberadas registradas em research.md. |

## Project Structure

### Documentation (this feature)

```text
specs/012-autos-processo-pacote/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/autos/
├── __init__.py
├── apps.py                  # AutosConfig
├── models.py                  # AutosPackageJob
├── admin.py
├── builder.py                # monta_pacote(job): fetch fresco, extração, loop de download,
│                              # placeholder, checagem de integridade, escrita do ZIP em disco
├── selectors.py                # job ativo/recente de um processo
├── services.py                # request_package(process, user), run_pending_packages(now)
│                              # — chamada pelo run_worker
├── views.py                    # pedir/consultar status/baixar (autenticado)
├── urls.py
├── migrations/
└── tests/
    ├── fixtures/                 # HTML/texto de processo com docs com/sem link, motivo
    │                              # declarado, um documento ZIP
    ├── test_builder.py
    └── test_services.py

apps/monitoring/management/commands/run_worker.py   # +1 chamada gated em _run_cycle
apps/processes/urls.py                                 # +3 rotas (pedir, status, download)
templates/processes/detail.html                        # +seção "Autos" (pedir/status/link)
config/settings.py                                      # +apps.autos, +env AUTOS_*, MEDIA_ROOT
config/env_schema.py                                    # TTL/expiração configurável
```

**Structure Decision**: App de domínio novo (`apps/autos/`), mesmo racional das features 009/010/
011 — a lógica de montagem de pacote (numeração, placeholder, integridade) é um domínio próprio,
não pertence a `apps/monitoring` (scraping/extração genérica) nem a `apps/processes` (CRUD do
processo). Reaproveita `apps/monitoring/clients.py` por composição (import direto das funções já
existentes), sem duplicar HTTP/extração.

## Complexity Tracking

*Nenhuma violação da constituição a justificar — todos os gates acima são PASS.*
