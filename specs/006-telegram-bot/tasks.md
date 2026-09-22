---

description: "Task list for 006-telegram-bot"
---

# Tasks: Bot do Telegram como canal principal

**Input**: Design documents from `/specs/006-telegram-bot/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Incluídos. São obrigatórios pela constituição (Princípio VII). A Bot API é sempre
mockada.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Criar o app `apps/telegram_bot/` (`__init__.py`, `apps.py` com `TelegramBotConfig`, `migrations/__init__.py`, `management/commands/__init__.py`) e registrar em `INSTALLED_APPS` (`config/settings.py`)
- [X] T002 Adicionar `TELEGRAM_*` e `BASE_URL` em `config/env_schema.py` (defaults, validação condicional quando habilitado, regex do secret, mínimos) e expor em `config/settings.py` (research R10)
- [X] T003 [P] Documentar `TELEGRAM_*` em `.env.example` (placeholders) conforme `contracts/webhook-and-ops.md`

---

## Phase 2: Foundational (bloqueia todas as stories)

- [X] T004 Models `TelegramChat`, `TelegramUpdate` e `BotAction` em `apps/telegram_bot/models.py` + migration (data-model.md)
- [X] T005 [P] `MonitoredProcess.origin` em `apps/processes/models.py` + migration
- [X] T006 [P] `ProcessSubscription.telegram_enabled` e `.paused` em `apps/subscribers/models.py` + migration
- [X] T007 [P] `NotificationChannel.TELEGRAM` em `apps/notifications/models.py` + migration
- [X] T008 [P] `apps/telegram_bot/client.py`: `TelegramResult`, `call(method, payload)`, `send_message`, `send_document`, `get_chat_member`, `get_me`, `set_webhook`, `delete_webhook`, `get_webhook_info`, `set_my_commands`. O token nunca vai para logs (research R1)
- [X] T009 [P] `apps/telegram_bot/parsing.py`: schemas pydantic (Update, Message, Chat, User, ChatMemberUpdated), `parse_command(text, bot_username)` e `normalize_process_ref()` (research R5, R8)
- [X] T010 [P] `apps/telegram_bot/messages.py`: textos pt-BR de todos os comandos e erros (contracts/bot-commands.md)
- [X] T011 [P] Testes em `tests/test_telegram_parsing.py`: normalização (canônico, 17 dígitos, espaços, URL do SEI, inválidos), `parse_command` (`/cmd`, `/cmd@NossoBot`, `/cmd@Outro` ignorado, args, texto livre)
- [X] T012 [P] Testes do cliente em `tests/test_telegram_channel.py`: payload JSON, `ok=false` → `TelegramResult` com `error_code`, erro de rede, token ausente de mensagens

**Checkpoint**: schema, parse e cliente prontos.

---

## Phase 3: User Story 1 — Começar a monitorar (P1) 🎯 MVP

**Goal**: `/start`, `/help` e `/watch` funcionando por webhook, com primeira leitura pelo worker.

**Independent Test**: quickstart §2 e §3, passos 1–4.

- [X] T013 [US1] `apps/telegram_bot/views.py` + `urls.py` (`POST /telegram/webhook/`), com secret via `compare_digest`, idempotência por `update_id` e 200 em caso de exceção. Incluir em `config/urls.py` (contracts/webhook-and-ops.md)
- [X] T014 [US1] `services.handle_update()`: ignorar canais, `get_or_create_chat` (criando `Subscriber` sem e-mail/WhatsApp), `last_seen_at`, dispatcher de comandos, envio da resposta. Handlers de `/start`, `/help` e fallback de texto livre
- [X] T015 [US1] `services.cmd_watch()`: normalização, limite por chat, duplicidade, criação/reuso do processo (`origin=telegram`, sem scraping), assinatura (`telegram_enabled=True`), `BotAction(initial_watch)` só sem baseline, resposta imediata com `latest_cade_records` quando já há baseline. `recalculate_process_status()` (research R6)
- [X] T016 [US1] `apps/monitoring/clients.py`: `lookup_process_url()` que propaga `FetchError`. `resolve_process_url` vira wrapper com o mesmo contrato (research R4)
- [X] T017 [US1] `apps/telegram_bot/actions.py::process_pending_bot_actions()`: agrupamento por processo, lookup + `run_check` uma vez, respostas por chat, "não encontrado" → cancela a assinatura e remove o processo órfão criado pelo bot, falha de rede → 3 tentativas rápidas e depois cadência normal (research R3)
- [X] T018 [US1] `run_worker._run_cycle`: `close_old_connections` → ações do bot (se `TELEGRAM_ENABLED`) → processos vencidos → `send_pending_notifications()` sempre (research R9)
- [X] T019 [P] [US1] Testes em `tests/test_telegram_webhook.py`: 404 desabilitado, 405, 403 sem ou com secret errado, 400 JSON inválido, idempotência (a mesma atualização duas vezes → um envio), exceção → 200
- [X] T020 [P] [US1] Testes em `tests/test_telegram_commands.py`: `/start` cria chat e assinante, `/start` reativa inalcançável, `/watch` válido (processo novo → ação; conhecido → resposta imediata), formato inválido, limite, duplicado, texto livre → ajuda
- [X] T021 [P] [US1] Testes em `tests/test_telegram_actions.py`: primeira leitura com sucesso responde as movimentações, não encontrado cancela e remove o órfão, falha de rede reagenda 3× rápido e depois cai para a cadência normal, sem expirar, dois chats no mesmo processo → um `run_check`
- [X] T022 [P] [US1] Teste em `tests/test_monitoring.py`: o worker envia notificações pendentes mesmo sem processos vencidos

**Checkpoint**: dá para começar a monitorar pelo Telegram.

---

## Phase 4: User Story 2 — Alertas no Telegram (P1) 🎯 MVP

**Goal**: mudanças detectadas viram alertas no Telegram pelo pipeline de notificações.

**Independent Test**: quickstart §4.

- [X] T023 [US2] `apps/notifications/channels/telegram.py`: `send_telegram_message` (corte em 4096 + link, 403/"chat not found" → `invalid_recipient` + chat inalcançável) e `send_telegram_document` (research R7)
- [X] T024 [US2] `apps/notifications/services.py`: ramo Telegram em `create_notifications_for_change` (condições do data-model), assinaturas `paused` ignoradas em todos os canais, ramo `telegram` em `_dispatch_payload` (mensagem principal + complemento + anexos, igual ao WhatsApp)
- [X] T025 [P] [US2] Testes em `tests/test_telegram_channel.py`: envio OK, corte em 4096, 403 marca o chat inalcançável, rede/429/5xx → `pending` (retentativa, research R9b), outros 4xx → `failed`, documento
- [X] T026 [P] [US2] Testes em `tests/test_notifications.py`: cria Notification Telegram para chat alcançável, não cria para pausado, inalcançável ou com `TELEGRAM_ENABLED=false`. Dispatch do Telegram registra `NotificationAttempt`. E-mail/WhatsApp inalterados (SC-007)

**Checkpoint**: MVP completo (US1 + US2).

---

## Phase 5: User Story 3 — Consultar e gerenciar (P2)

**Goal**: `/list`, `/status`, `/history` e `/unwatch`.

**Independent Test**: quickstart §3, passos 5, 6, 8 e 11.

- [X] T027 [US3] `apps/telegram_bot/selectors.py`: `chat_subscriptions(chat)`, `find_chat_subscription(chat, ref)`, `process_history(process, limit)`
- [X] T028 [US3] Handlers `cmd_list`, `cmd_status`, `cmd_history` e `cmd_unwatch` (com `recalculate_process_status`), mais a resposta padrão "não acompanha" (FR-010)
- [X] T029 [P] [US3] Testes em `tests/test_telegram_commands.py`: lista vazia ou com itens, status, histórico com limite e ordem, unwatch (o processo `telegram` fica PAUSED sem assinantes; o do `panel` não muda), processo de outro chat → "não acompanha" (SC-006)

---

## Phase 6: User Story 4 — Pausar, retomar, forçar verificação (P3)

**Goal**: `/pause`, `/resume` e `/check` com intervalo mínimo.

**Independent Test**: quickstart §3, passos 7, 9 e 10.

- [X] T030 [US4] Handlers `cmd_pause`, `cmd_resume` e `cmd_check` (intervalo mínimo por `last_checked_at`, uma ação pendente por chat e processo)
- [X] T031 [US4] Em `actions.py`: resposta das ações `check` ("sem novidades" ou resumo da mudança). A ação `check` cujo processo acabou de ser verificado responde com o estado salvo
- [X] T032 [P] [US4] Testes: pause e resume isolados por chat, pausa não gera alerta, `/check` dentro do intervalo (sem ação, com tempo restante), fora (cria ação), dois chats → uma consulta, mudança por `/check` notifica os outros chats

---

## Phase 7: User Story 5 — Grupos (P3)

**Goal**: bot em grupos, com gestão restrita a administradores.

**Independent Test**: quickstart §5.

- [X] T033 [US5] Em `handle_update`: verificação de admin via `get_chat_member` para comandos de gestão em grupo, `my_chat_member` (sair/ser removido → inalcançável; voltar → alcançável), `migrate_to_chat_id` (atualiza o `chat_id`), `/cmd@Outro` ignorado (research R8)
- [X] T034 [P] [US5] Testes: admin pode `/watch`, membro é recusado em `/watch`/`/unwatch`/`/pause`/`/resume`, membro pode `/list`/`/status`/`/check`, falha no `getChatMember` → recusa, `my_chat_member` kicked/left/member, migração para supergrupo preserva as assinaturas, `/list@NossoBot` e `/list@Outro`

---

## Phase 8: Polish & Cross-Cutting

- [X] T035 `apps/telegram_bot/management/commands/telegram_webhook.py` (set + `setMyCommands`, `--info`, `--delete`, `--url`) + testes com cliente mockado
- [X] T036 [P] `apps/telegram_bot/admin.py` (TelegramChat com assinaturas inline e somente leitura, BotAction, TelegramUpdate). Mostrar `paused`/`telegram_enabled` em `apps/subscribers/admin.py`
- [X] T037 [P] `cleanup_snapshots`: remover `TelegramUpdate` com mais de 30 dias e `BotAction` finalizadas com mais de 30 dias
- [X] T038 [P] `README.md`: seção "Bot do Telegram" (BotFather, env, `telegram_webhook`, comandos, grupos), stack e variáveis. Atualizar o ⚠ restante do Sync Impact Report em `.specify/memory/constitution.md`
- [X] T039 Rodar a suíte completa e `makemigrations --check`
- [ ] T040 ⏳ *Pendente: depende do deploy no Render e de um bot real (dono do projeto).* Validação manual do `quickstart.md` §2–§6 com um bot real (depende do deploy no Render, feito pelo dono)

---

## Dependencies & Execution Order

- Setup → Foundational → US1 → US2 (MVP). US3, US4 e US5 dependem de US1 (dispatcher e chat) e
  podem seguir em qualquer ordem depois dela. US4 também depende de `actions.py` (T017).
- T013 depende de T014 (view → service). T017 depende de T016. T024 depende de T023.

## Parallel Example

```text
Phase 2: T005 | T006 | T007 | T008 | T009 | T010   (arquivos distintos)
US1 testes: T019 | T020 | T021 | T022
```

## Implementation Strategy

1. **MVP** = Phases 1–4: autoatendimento com `/watch` e alertas.
2. Em seguida, US3 (gestão), US4 (pausa/check) e US5 (grupos).
3. Polish, com o comando de webhook que viabiliza o deploy.
