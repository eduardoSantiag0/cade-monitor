# Data Model: Bot do Telegram

**Feature**: [spec.md](./spec.md) | **Date**: 2026-09-22

## Novo app `telegram_bot`

### TelegramChat
Conversa em que o bot atua (privado ou grupo). Cada chat é um `Subscriber`.

| Campo | Tipo | Regras |
|---|---|---|
| `chat_id` | BigInteger | unique. Muda em migração para supergrupo |
| `chat_type` | Char(20) | `private` \| `group` \| `supergroup` |
| `title` | Char(255) | nome da pessoa ou título do grupo (truncado) |
| `username` | Char(64) | opcional |
| `is_reachable` | Boolean | default True. False após bloqueio/remoção/403 |
| `subscriber` | OneToOne → `subscribers.Subscriber` | CASCADE. Criado no primeiro contato |
| `created_at` / `updated_at` / `last_seen_at` | DateTime | |

Transições de `is_reachable`: True → False com 403 no envio, `my_chat_member` = left/kicked.
False → True com `/start` ou quando o bot volta a ser membro.

### TelegramUpdate
| Campo | Tipo | Regras |
|---|---|---|
| `update_id` | BigInteger | unique (idempotência) |
| `received_at` | DateTime | auto. Limpeza de registros antigos (>30 dias) no `cleanup_snapshots` |

### BotAction
Pedido que depende de consulta ao SEI, executado pelo `run_worker`.

| Campo | Tipo | Regras |
|---|---|---|
| `kind` | Char(20) | `initial_watch` \| `check` |
| `chat` | FK → TelegramChat | CASCADE |
| `process` | FK → processes.MonitoredProcess | CASCADE |
| `status` | Char(20) | `pending` → `done` \| `failed` \| `cancelled` |
| `attempts` | PositiveSmallInteger | default 0. Máximo de 3 para `initial_watch` |
| `next_attempt_at` | DateTime | default now. O worker só pega ações com `next_attempt_at <= now` |
| `result_message` | Text | última resposta ou erro (auditoria) |
| `requested_at` / `finished_at` | DateTime | |

Índice: (`status`, `next_attempt_at`). Unicidade lógica: no máximo uma ação `pending` por
(`chat`, `process`, `kind`), garantida no service.

## Mudanças em entidades existentes

| Entidade | Campo novo | Tipo / default | Uso |
|---|---|---|---|
| `processes.MonitoredProcess` | `origin` | Char(20), `panel` \| `telegram`, default `panel` | O bot só gerencia o status de processos `telegram` (research R6) |
| `subscribers.ProcessSubscription` | `telegram_enabled` | Boolean, default False | Canal Telegram por assinatura (True nas criadas pelo bot) |
| `subscribers.ProcessSubscription` | `paused` | Boolean, default False | `/pause`. Ignorada em todos os canais |
| `notifications.NotificationChannel` | `TELEGRAM = 'telegram'` | choice | `destination` = `chat_id` em texto |

Todas as colunas novas têm default, então as migrations são aditivas e seguras com dados
existentes.

## Regras derivadas

- Quantidade de processos de um chat = assinaturas do `subscriber` do chat (pausadas contam).
  Limite: `TELEGRAM_MAX_PROCESSES_PER_CHAT`.
- Um processo `origin=telegram` fica `ACTIVE` quando tem ≥1 assinatura com `paused=False`, e
  `PAUSED` quando não tem nenhuma (research R6).
- Um alerta Telegram é criado quando: `TELEGRAM_ENABLED`, `sub.telegram_enabled`,
  `not sub.paused`, `subscriber.is_reachable()` e existe `subscriber.telegram_chat` com
  `is_reachable`.
