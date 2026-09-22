# Quickstart: Bot do Telegram

**Feature**: [spec.md](./spec.md) | Contratos: [bot-commands](./contracts/bot-commands.md),
[webhook-and-ops](./contracts/webhook-and-ops.md)

## Pré-requisitos

1. Criar o bot no **@BotFather** (`/newbot`) e guardar o token.
2. Gerar o secret do webhook: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
3. Nas env vars do Render (web **e** worker), e também no `.env` local, se for o caso:
   ```
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=<token do BotFather>
   TELEGRAM_WEBHOOK_SECRET=<secret gerado>
   BASE_URL=https://<seu-app>.onrender.com
   ```
4. Fazer o deploy e rodar `python manage.py migrate`.

## 1. Testes automatizados

```bash
python manage.py test tests
```

**Esperado**: toda a suíte passa, incluindo `test_telegram_*` e os testes existentes de
e-mail/WhatsApp (SC-007).

## 2. Registrar o webhook

```bash
python manage.py telegram_webhook          # setWebhook + setMyCommands
python manage.py telegram_webhook --info   # deve mostrar a URL e pending_update_count=0
```

**Esperado**: a URL é `<BASE_URL>/telegram/webhook/`, sem `last_error_message`. No Telegram, o
menu `/` mostra os comandos.

Verificação de segurança:

```bash
curl -i -X POST <BASE_URL>/telegram/webhook/ -d '{}'
```

**Esperado**: `403`, porque a requisição não tem o secret.

## 3. Fluxo privado (User Stories 1–4)

| Passo | Envie | Esperado |
|---|---|---|
| 1 | `/start` | apresentação + comandos |
| 2 | `/watch 08700.005905/2026-38` | "🔎 Consultando…", seguido em segundos de "✅ Monitorando" + últimas movimentações |
| 3 | `/watch 08700005905202638` | "Você já acompanha…" (normalização) |
| 4 | `/watch 123` | erro de formato com exemplo |
| 5 | `/list` | 1 processo ▶️ com a última verificação |
| 6 | `/status 08700.005905/2026-38` | última movimentação e datas |
| 7 | `/check 08700.005905/2026-38` | dentro do intervalo mínimo: estado salvo + "tente em N min" |
| 8 | `/history 08700.005905/2026-38` | até 5 mudanças ou "nenhuma mudança registrada ainda" |
| 9 | `/pause …` e depois `/list` | ⏸️ |
| 10 | `/resume …` | ▶️ |
| 11 | `/unwatch …` e depois `/list` | lista vazia + dica de `/watch` |

## 4. Alerta (User Story 2)

Em dev, com um processo acompanhado pelo seu chat: altere `last_hash` do processo no admin (ou
edite o último `PageSnapshot`) e rode `python manage.py run_worker --once`, depois que o processo
vencer, ou use `/check` fora do intervalo mínimo.

**Esperado**: a mensagem de alerta chega no chat, e em `/notifications` aparece uma
`Notification` do canal Telegram com status `sent` e o `NotificationAttempt` registrado.

## 5. Grupo (User Story 5)

1. Adicione o bot a um grupo de teste.
2. Um **administrador** envia `/watch <proc>`. **Esperado**: o processo passa a ser acompanhado
   pelo grupo.
3. Um **membro comum** envia `/unwatch <proc>`. **Esperado**: recusa ("só administradores").
4. Um membro comum envia `/list@<SeuBot>`. **Esperado**: a lista do grupo.
5. Remova o bot do grupo. **Esperado**: no admin, o `TelegramChat` do grupo fica com
   `is_reachable=False`.

## 6. Edge cases

- Reenvie o mesmo JSON de atualização duas vezes para o webhook (com o secret). **Esperado**:
  uma única resposta no chat.
- Bloqueie o bot no privado e force um alerta. **Esperado**: a notificação fica
  `invalid_recipient` e o chat fica inalcançável. Depois desbloqueie e envie `/start`.
  **Esperado**: o chat volta a ser alcançável e mantém os processos.
