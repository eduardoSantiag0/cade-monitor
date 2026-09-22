# Implementation Plan: Bot do Telegram como canal principal

**Branch**: `006-telegram-bot` | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-telegram-bot/spec.md`

## Summary

Bot do Telegram por webhook, para conversas privadas e grupos, com autoatendimento completo
(`/start`, `/watch`, `/unwatch`, `/list`, `/status`, `/check`, `/pause`, `/resume`,
`/history`) e alertas de mudança como novo canal de notificação.

Abordagem:
- Novo app `telegram_bot` com cliente HTTP em stdlib, webhook fino e idempotente, e services
  com um handler por comando.
- Cada chat vira um `Subscriber`. Assim o pipeline existente (`Notification` →
  `NotificationAttempt` → retentativas → anexos) ganha o canal `telegram` sem mudança
  estrutural.
- O que depende do SEI (primeira leitura e `/check`) vira `BotAction` e é executado pelo
  `run_worker`, com uma consulta por processo por tick e intervalo mínimo no `/check`.

## Technical Context

**Language/Version**: Python 3.11 (dev) / 3.12 (imagem e CI).

**Primary Dependencies**: Django 5.2, pydantic 2 (schemas das atualizações e das settings),
stdlib `urllib` para a Bot API. **Nenhuma dependência nova.**

**Storage**: PostgreSQL 18 (produção, feature 005) / SQLite (dev e testes). Três tabelas novas e
três colunas novas, todas aditivas.

**Testing**: `python manage.py test tests`. Bot API sempre mockada (sem HTTP real). Webhook
testado com o `Client` do Django.

**Target Platform**: Render (web Gunicorn 1×2 + worker `run_worker`), com HTTPS público para o
webhook.

**Project Type**: Web service Django monolítico.

**Performance Goals**: Primeira resposta a qualquer comando em ≤5 s (SC-002). Resposta do
worker em ≤ 1 tick + tempo de consulta ao SEI.

**Constraints**:
- Nenhum scraping no request.
- No máximo 1 consulta ao SEI por processo por tick.
- `/check` respeita um intervalo mínimo de 5 min por processo.
- Mensagens de até 4096 caracteres.
- Token e secret só no ambiente.

**Scale/Scope**: Dezenas a centenas de chats. Limite de 10 processos por chat.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* Referência:
constituição **v2.0.0**.

| Princípio | Verificação | Status |
|---|---|---|
| I. Simplicidade Operacional | Webhook dentro do Gunicorn. Ações pesadas em `BotAction`, lidas pelo `run_worker` (tabela no banco, sem fila externa). Nenhum processo novo. | ✅ |
| II. Monitoramento Responsável | Periodicidade intocada. `/check` com intervalo mínimo e agrupado por processo. Primeira leitura com no máximo 3 tentativas espaçadas. Uma consulta por processo por tick. | ✅ |
| III. Django Monolítico | Novo app `telegram_bot` (já previsto na v2.0.0). Lógica em `services.py`/`selectors.py`. View só valida e delega. | ✅ |
| IV. PostgreSQL | Migrations aditivas e portáveis. Nada de SQL específico. | ✅ |
| V. Notificações | Canal em `notifications/channels/telegram.py` com retorno `(status, error)`. Bot API via `urllib`. Secret validado com `compare_digest`. Idempotência por `update_id`. `NotificationAttempt` registrado. | ✅ |
| VI. Humanização | Textos em pt-BR centralizados em `messages.py`. Alertas reaproveitam o template híbrido. Sem alerta antes da baseline (a primeira leitura não notifica). | ✅ |
| VII. Qualidade | Testes de parsing, de cada comando (caminho feliz e erro), do webhook (403/400/idempotência), de grupos, das ações do worker, do canal e da não regressão de e-mail/WhatsApp. | ✅ |
| VIII. Sem Over-Engineering | Zero dependências novas. Sem SDK, sem long polling. Sem vínculo com assinantes antigos (fora do escopo da v1). | ✅ |

**Post-design re-check (Phase 1)**: ✅. O único ponto sensível é o `BotAction`, que funciona
como uma "fila". Ele segue o padrão já aceito de `Notification` pendente e está explicitamente
permitido pelo Princípio I da v2.0.0.

## Project Structure

### Documentation (this feature)

```text
specs/006-telegram-bot/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── bot-commands.md
│   └── webhook-and-ops.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
apps/telegram_bot/                 # NOVO app
├── __init__.py / apps.py
├── models.py                      # TelegramChat, TelegramUpdate, BotAction
├── migrations/0001_initial.py
├── client.py                      # Bot API via urllib → TelegramResult
├── parsing.py                     # schemas pydantic do Update, parse_command, normalize_process_ref
├── messages.py                    # textos pt-BR
├── selectors.py                   # assinaturas do chat, busca por ref, histórico
├── services.py                    # handle_update + handlers + regras de status (R6)
├── actions.py                     # process_pending_bot_actions() (worker)
├── views.py / urls.py             # POST /telegram/webhook/
├── admin.py
└── management/commands/telegram_webhook.py

apps/notifications/
├── models.py                      # + NotificationChannel.TELEGRAM (+ migration)
├── channels/telegram.py           # NOVO: send_telegram_message / send_telegram_document
└── services.py                    # ramo telegram em create_notifications_for_change e _dispatch_payload; pula paused

apps/subscribers/models.py         # ProcessSubscription.telegram_enabled, .paused (+ migration)
apps/processes/models.py           # MonitoredProcess.origin (+ migration)
apps/monitoring/clients.py         # lookup_process_url() (R4); resolve_process_url vira wrapper
apps/monitoring/management/commands/run_worker.py     # ações do bot → vencidos → notificações sempre (R9)
apps/monitoring/management/commands/cleanup_snapshots.py  # + limpeza de TelegramUpdate > 30 dias

config/env_schema.py, config/settings.py, config/urls.py   # TELEGRAM_*, BASE_URL, app e rota
templates/notifications/list.html  # (sem mudança: usa get_channel_display)
.env.example, README.md

tests/
├── test_telegram_parsing.py
├── test_telegram_commands.py
├── test_telegram_webhook.py
├── test_telegram_actions.py
└── test_telegram_channel.py       # + ramos em test_notifications.py
```

**Structure Decision**: Novo app de domínio `telegram_bot`, conforme o Princípio III. O canal de
envio fica em `notifications/channels/`, conforme o Princípio V, e reaproveita o `client.py` do
app do bot, para existir um único ponto de contato com a Bot API.

## Design Notes

1. **Fluxo do webhook**: `views.telegram_webhook` → validações (contracts/webhook-and-ops.md)
   → `services.handle_update(payload)`. Dentro dele:
   - `parsing.parse_update()`;
   - ignora `channel_post`;
   - trata `my_chat_member` (alcançável ou não) e `migrate_to_chat_id`;
   - para mensagens com texto, chama `parse_command(text, bot_username)`, faz
     `get_or_create_chat()`, verifica admin quando o comando é de gestão e está num grupo,
     executa o handler e responde com `client.send_message`.
2. **Handlers** retornam o texto da resposta, o que deixa tudo testável sem enviar nada.
   `handle_update` é quem envia.
3. **`/watch`**:
   - `normalize_process_ref` → procura `MonitoredProcess` por `source`;
   - se não existir, cria direto (sem `_try_resolve_url`, que faria scraping no request) com
     `origin=telegram`;
   - verifica o limite e a duplicidade;
   - `ProcessSubscription(telegram_enabled=True, email_enabled=False, whatsapp_enabled=False)`;
   - se `not process.has_baseline`: cria `BotAction(initial_watch)`. Caso contrário, responde na
     hora com `latest_cade_records(process.last_text)`;
   - `recalculate_process_status(process)`.
4. **`actions.process_pending_bot_actions()`**:
   - seleciona as ações `pending` com `next_attempt_at <= now` e agrupa por processo;
   - para cada processo, se ainda não tem `resolved_url` e o `source` não é URL:
     `lookup_process_url` (R4);
   - `run_check(process)` uma única vez;
   - monta a resposta por `kind` e envia para cada chat;
   - marca `done`/`failed`, ou reagenda (R3).
   - Antes da consulta, uma ação `check` cujo processo foi verificado dentro do intervalo mínimo
     (por outra ação ou pela agenda) é respondida com o estado salvo.
5. **Status do processo** (R6): `services.recalculate_process_status(process)` é chamado depois
   de `/watch`, `/unwatch`, `/pause`, `/resume` e do cancelamento de uma assinatura inexistente.
6. **Canal**: `send_telegram_message(chat_id, body)` corta em 4096 caracteres. Se a API
   responder 403 (ou 400 "chat not found"), marca o `TelegramChat` como inalcançável e retorna
   `invalid_recipient`. 429 e erro de rede retornam `failed` (retentativa normal).
   `send_telegram_document(chat_id, url, filename)`.
7. **Worker** (R9): chama `close_old_connections()` → ações do bot (se habilitado) → processos
   vencidos → `send_pending_notifications()` sempre.

## Complexity Tracking

Sem violações. Seção não aplicável.
