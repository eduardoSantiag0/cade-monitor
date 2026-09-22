# Contract: Webhook, comando operacional e configuração

## `POST /telegram/webhook/`

| Condição | Status HTTP | Efeito |
|---|---|---|
| `TELEGRAM_ENABLED=false` | 404 | nenhum |
| método ≠ POST | 405 | nenhum |
| header `X-Telegram-Bot-Api-Secret-Token` ausente ou diferente | 403 | nenhum |
| corpo não é JSON ou não tem `update_id` | 400 | nenhum |
| `update_id` já processado | 200 | nenhum (idempotente) |
| atualização válida | 200 | processada (`handle_update`) |
| exceção ao processar | 200 | erro logado (Sentry), atualização marcada como recebida |

Sem autenticação Django, com `csrf_exempt`. A resposta é sempre `{"ok": true}` ou vazia.

## `python manage.py telegram_webhook`

| Opção | Ação |
|---|---|
| *(nenhuma)* | `setWebhook(url=<BASE_URL>/telegram/webhook/, secret_token, allowed_updates=["message","my_chat_member"], drop_pending_updates=false)` + `setMyCommands` (pt-BR) |
| `--info` | mostra o `getWebhookInfo` (url, pending_update_count, last_error_message) |
| `--delete` | `deleteWebhook` |
| `--url URL` | sobrescreve a base (ex.: túnel em dev) |

Retorna exit ≠ 0 se a API responder `ok=false` ou se `TELEGRAM_BOT_TOKEN`/`BASE_URL` não estiverem
configurados. O token nunca é impresso.

## Variáveis de ambiente

| Variável | Tipo | Padrão | Observação |
|---|---|---|---|
| `TELEGRAM_ENABLED` | bool | `false` | liga o webhook e os alertas |
| `TELEGRAM_BOT_TOKEN` | str | `''` | obrigatório se habilitado (@BotFather) |
| `TELEGRAM_WEBHOOK_SECRET` | str | `''` | obrigatório se habilitado. `^[A-Za-z0-9_-]{16,256}$` |
| `TELEGRAM_BOT_USERNAME` | str | `''` | opcional. Se vazio, vem do `getMe` |
| `TELEGRAM_MAX_PROCESSES_PER_CHAT` | int ≥1 | `10` | |
| `TELEGRAM_CHECK_COOLDOWN_SECONDS` | int ≥60 | `300` | também é o intervalo entre retentativas da primeira leitura |
| `TELEGRAM_HISTORY_LIMIT` | int ≥1 | `5` | |
| `TELEGRAM_TIMEOUT_SECONDS` | int | `10` | timeout das chamadas à Bot API |
| `BASE_URL` | URL | `''` | já está no `.env.example`, mas as settings ainda não a liam. Passa a ser lida. É a base pública usada pelo `telegram_webhook` |
