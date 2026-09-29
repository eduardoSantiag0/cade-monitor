# Implementation Plan: Comando /preview — demonstração para portfólio

**Branch**: `014-comando-preview-demonstracao` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-comando-preview-demonstracao/spec.md`

## Summary

Novo comando `/preview` no bot do Telegram, cujo handler só chama um caso de uso dedicado
(`RunDemoUseCase`, em `apps/telegram_bot/demo.py`) que: (1) obtém (ou cria, na primeira vez) um
único `MonitoredProcess` fictício reservado, permanentemente `status=ARCHIVED` (nunca entra no
ciclo real do `run_worker`/`get_due_processes`); (2) usa dois textos fixos (andamento anterior/
novo) como cenário, sem nenhuma chamada de rede; (3) reaproveita `compute_diff` (função pura já
existente em `apps/monitoring/diff.py`) para gerar o resumo da mudança, exatamente como uma
checagem real geraria; (4) reaproveita a formatação de notificação já existente
(`apps/notifications/services.py::build_test_notification_body`, já usada pelo botão "enviar
e-mail de teste" do painel) para gerar um exemplo de conteúdo de notificação; (5) monta e devolve
o texto de resposta do Telegram — nunca chama `get_snapshot`, `collect_new_documents`, nem
qualquer função de envio real de notificação.

## Technical Context

**Language/Version**: Python 3.11 (Django 5.2.15).

**Primary Dependencies**: Nenhuma nova — reaproveita `apps.monitoring.diff.compute_diff` e
`apps.notifications.services.build_test_notification_body`, ambas funções puras já existentes.

**Storage**: Reaproveita `apps.processes.models.MonitoredProcess` (sem alteração de schema) e,
opcionalmente, `apps.monitoring.models.DetectedChange`/`CheckRun`/`PageSnapshot` (sem alteração de
schema) para o único registro de demonstração — get-or-create/update-in-place, nunca cria um
segundo registro fictício.

**Testing**: `django.test.TestCase`, com mock estrito de qualquer função de rede (falha o teste se
`urllib.request.urlopen`/`get_snapshot`/qualquer client HTTP for chamado) — prova estrutural de
FR-006/SC-002.

**Target Platform**: Linux (Docker/Render), mesmo webhook Gunicorn já existente — comando roda
inteiramente síncrono no request do webhook (sem I/O externo, não precisa do padrão "vira
BotAction para o run_worker" usado por `/check`/`/watch`).

**Project Type**: Web service (monolito Django) — novo módulo dentro do app `telegram_bot` já
existente.

**Performance Goals**: Resposta em até 3s (SC-001) — trivialmente atendido, já que não há I/O de
rede nem espera alguma.

**Constraints**: Sem dependência nova (Princípio VIII); sem requisição de rede (FR-006); sem envio
real de notificação (FR-007); processo fictício permanentemente isolado do ciclo de monitoramento
real (FR-008).

**Scale/Scope**: Um único registro fictício reutilizado para sempre — sem relação com o número de
processos reais monitorados.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
|---|---|
| I. Simplicidade Operacional | **PASS** — sem processo/worker novo; roda síncrono no webhook (não precisa de BotAction/run_worker, já que não há I/O externo — a exceção do "webhook nunca faz scraping" não se aplica porque não há scraping algum aqui). |
| II. Monitoramento Responsável | **PASS/N/A** — nenhuma fonte externa é consultada (FR-006); nada a avaliar quanto a cadência. |
| III. Django Monolítico Bem Organizado | **PASS** — lógica de negócio isolada num módulo de caso de uso dentro do app `telegram_bot` já existente (FR-012); handler do comando (`services.py::cmd_preview`) só chama o caso de uso e devolve o texto. |
| IV. PostgreSQL em Produção | **PASS** — nenhuma migration nova (reaproveita modelos existentes sem alteração de schema). |
| V. Notificações | **PASS** — não envia notificação real por nenhum canal (FR-007); reaproveita só a função de *formatação* de mensagem, não a de envio. |
| VI. Humanização das Mensagens | **PASS** — resposta em português natural, claramente rotulada como demonstração. |
| VII. Portfólio-Ready | **PASS** — é, literalmente, a feature que reforça o caráter de portfólio do projeto; testes cobrindo cada garantia de segurança (sem rede, sem envio real, idempotência). |
| VIII. Sem Over-Engineering | **PASS** — sem dependência nova; reaproveita funções puras já existentes em vez de duplicar lógica de diff/formatação. |

## Project Structure

### Documentation (this feature)

```text
specs/014-comando-preview-demonstracao/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/telegram_bot/
├── demo.py                    # NOVO: RunDemoUseCase — cenário fixo, compute_diff, formatação,
│                              # get-or-create do processo/mudança fictícios
├── client.py                    # +('preview', '🧪 Ver uma demonstração do sistema') em BOT_COMMANDS
├── services.py                  # +cmd_preview(chat, args) -> str (chama RunDemoUseCase.run())
│                              # +registro em COMMANDS
└── tests/
    └── test_demo.py              # NOVO: cobre FR-002 a FR-010

README.md                          # +seção "Modo de demonstração" (FR-011)
```

**Structure Decision**: `RunDemoUseCase` vive em `apps/telegram_bot/demo.py` (não em
`apps/monitoring` nem `apps/notifications`) porque é especificamente uma dramatização do fluxo
para fins de portfólio — não é lógica de monitoramento nem de notificação em si, é composição das
duas, iniciada e consumida só pelo bot. Reaproveita `compute_diff`/`build_test_notification_body`
por import direto (composição), sem duplicar nenhuma das duas.

## Complexity Tracking

*Nenhuma violação da constituição a justificar — todos os gates acima são PASS.*
