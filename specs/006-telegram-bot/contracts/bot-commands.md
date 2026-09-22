# Contract: Comandos do bot

`<proc>` = número SEI (`08700.005905/2026-38`, com ou sem pontuação) ou link público do SEI do
CADE. Em grupos, os comandos também são aceitos no formato `/cmd@NomeDoBot`.

| Comando | Quem (grupo) | Validações | Efeito | Resposta imediata | Resposta do worker |
|---|---|---|---|---|---|
| `/start` | todos | — | cria ou reativa o chat/assinante, `is_reachable=True` | apresentação + comandos | — |
| `/help` | todos | — | — | lista de comandos | — |
| `/watch <proc>` | admin | formato; limite do chat; não duplicado | cria/reaproveita o processo (`origin=telegram` se novo), a assinatura (`telegram_enabled=True`) e, se o processo não tem baseline, uma `BotAction(initial_watch)` | processo novo: "🔎 Consultando…". Já conhecido: "✅ Monitorando" + última movimentação | "✅ Monitorando…" + últimas movimentações \| "❌ não encontrado/não público" \| "⚠️ SEI indisponível, vou tentar de novo" |
| `/unwatch <proc>` | admin | chat acompanha | remove a assinatura e recalcula o status (R6) | "Você não acompanha mais…" | — |
| `/list` | todos | — | — | processos com ▶️/⏸️ e última verificação, ou dica de `/watch` | — |
| `/status <proc>` | todos | chat acompanha | — | última movimentação detectada + últimas verificação e mudança | — |
| `/check <proc>` | todos | chat acompanha | dentro do intervalo mínimo: nada. Fora dele: `BotAction(check)` (uma pendente por chat e processo) | dentro: estado salvo + "tente em N min". Fora: "🔎 Verificando agora…" | "Sem novidades desde …" \| resumo da mudança (os outros chats recebem o alerta normal) |
| `/pause <proc>` | admin | chat acompanha | `paused=True` e recalcula o status | "⏸️ Alertas pausados…" | — |
| `/resume <proc>` | admin | chat acompanha | `paused=False` e recalcula o status | "▶️ Alertas retomados…" | — |
| `/history <proc>` | todos | chat acompanha | — | até `TELEGRAM_HISTORY_LIMIT` mudanças (mais recente primeiro) | — |
| texto livre ou comando desconhecido | todos | — | — | ajuda resumida | — |

## Erros padronizados

| Situação | Resposta |
|---|---|
| sem argumento | "Informe o número do processo. Ex.: /watch 08700.005905/2026-38" |
| formato inválido | "Número inválido. Use o formato 08700.005905/2026-38 ou o link do SEI." |
| não acompanha | "Você não acompanha o processo X. Use /list para ver os seus." |
| limite atingido | "Você já acompanha N processos (limite). Use /unwatch para liberar espaço." |
| não é admin (grupo) | "Neste grupo, só administradores podem usar /cmd." |
| canal (broadcast) | atualização ignorada, sem resposta |
