# Research: Bot do Telegram como canal principal

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-09-22

## R1 — Cliente da Bot API

- **Decision**: Módulo `apps/telegram_bot/client.py` com `urllib.request` (POST JSON para
  `https://api.telegram.org/bot<token>/<method>`). Retorna um `TelegramResult(ok, result,
  error_code, description)` e **nunca lança** por erro HTTP da API. Erros de rede viram
  `ok=False, error_code=None`. O token nunca aparece em logs nem em mensagens de erro.
- **Rationale**: Constituição v2.0.0, Princípio V (sem SDK) e o mesmo padrão de
  `channels/evolution.py`. Métodos usados: `sendMessage`, `sendDocument`, `getChatMember`,
  `getMe`, `setWebhook`, `deleteWebhook`, `getWebhookInfo`, `setMyCommands`.
- **Alternatives considered**: `python-telegram-bot` / `aiogram` (SDKs assíncronos e pesados,
  proibidos pela constituição).

## R2 — Webhook: autenticação, idempotência e tempo de resposta

- **Decision**: `POST /telegram/webhook/`, com `csrf_exempt`, sem login. Fluxo:
  1. Retorna 404 se `TELEGRAM_ENABLED=false`.
  2. Compara `X-Telegram-Bot-Api-Secret-Token` com `TELEGRAM_WEBHOOK_SECRET` usando
     `hmac.compare_digest`. Se não bater, retorna 403.
  3. Faz o parse do JSON. Se for inválido, retorna 400.
  4. `TelegramUpdate.objects.get_or_create(update_id=...)` dentro de `transaction.atomic`. Se a
     atualização já existia, retorna 200 sem efeito.
  5. Chama `services.handle_update()`. Exceções são logadas (Sentry) e o webhook **retorna 200
     mesmo assim**, para o Telegram não reentregar indefinidamente uma atualização que sempre
     falha.
- **Rationale**: FR-003, SC-005. O Telegram reenvia a atualização quando não recebe 2xx. O
  webhook só faz operações de banco e 1 ou 2 chamadas à Bot API (`sendMessage`, e
  `getChatMember` em grupo), que respondem em milissegundos e cabem no SC-002. Scraping
  **nunca** acontece no request (Princípio I).
- **Alternatives considered**: responder usando o corpo do webhook (o "método na resposta" do
  Telegram). Economiza uma chamada, mas não informa falha de envio e complica os testes.
  Long polling foi descartado pelo dono do projeto.

## R3 — Ações que dependem do SEI (primeira leitura e /check)

- **Decision**: Tabela `telegram_bot.BotAction` (`kind` = `initial_watch` | `check`, `status` =
  `pending` | `done` | `failed` | `cancelled`, `attempts`, `next_attempt_at`). O `run_worker`
  processa as ações **no início de cada tick**, antes da agenda normal, agrupando por processo:
  **uma** consulta ao SEI por processo por tick, e a resposta vai para todos os chats que pediram
  (SC-004).
- **Rationale**: Princípio I (sem fila externa; é o mesmo padrão das `Notification` pendentes).
  Com `WORKER_TICK_SECONDS=5`, a resposta final chega em segundos.
- **Retentativa da primeira leitura**: se houver falha de rede, a ação é reagendada
  (`next_attempt_at = agora + TELEGRAM_CHECK_COOLDOWN_SECONDS`) nas 3 primeiras tentativas.
  Depois, ela continua pendente, mas passa a ser tentada na cadência normal
  (`CHECK_INTERVAL_SECONDS`, ≥25 min). O chat é avisado na 1ª falha e na passagem para a
  cadência normal, e recebe "✅ Monitorando" quando a baseline finalmente sair (edge case "site
  fora do ar"). A ação não expira sozinha: termina com sucesso, com "não encontrado" ou com
  `/unwatch`.
  *Ajuste feito na implementação:* `_mark_failed` coloca o processo em `ERROR`, e a agenda
  normal ignora processos nesse estado. Se a ação expirasse, o processo ficaria sem baseline
  para sempre.
- **/check que encontra mudança**: o chat que pediu recebe "encontrei movimentação, o alerta
  vem a seguir". O alerta completo sai pelo fluxo normal de `Notification` no mesmo tick, sem
  duplicar o conteúdo.

## R4 — Processo inexistente vs. falha de rede

- **Finding**: `clients._fetch_by_process_number` **não falha** para um número inexistente. Ele
  devolve a própria página de pesquisa como snapshot. Já `resolve_process_url` engole
  `FetchError` e retorna `None`, então não dá para distinguir "não existe" de "rede caiu".
- **Decision**: Nova função `clients.lookup_process_url(number, timeout, user_agent) -> str | None`,
  que **propaga** `FetchError` (rede/HTTP) e retorna `None` só quando a busca deu certo mas não
  achou link de detalhe (processo inexistente ou não público). `resolve_process_url` passa a ser
  um wrapper dela e mantém o contrato atual. Na ação `initial_watch` de um processo novo:
  `None` → avisa "não encontrado ou não público", cancela a assinatura e remove o processo se
  ele foi criado pelo bot e não tem outras assinaturas. `FetchError` → retentativa (R3).
  URL resolvida → grava `resolved_url` e chama `run_check`.

## R5 — Formato e normalização do número

- **Decision**: `parsing.normalize_process_ref(text)` retorna o número canônico
  `NNNNN.NNNNNN/AAAA-DD` ou uma URL `https://sei.cade.gov.br/...`. Regras:
  - remove espaços;
  - aceita 17 dígitos sem pontuação (ex.: `08700005905202638` → `08700.005905/2026-38`);
  - aceita a forma canônica;
  - aceita URLs cujo host termina em `cade.gov.br`.
  O `source` do `MonitoredProcess` usa a forma canônica, então `/watch 08700005905202638` e
  `/watch 08700.005905/2026-38` apontam para o mesmo processo (`source` é unique).
- **Rationale**: Edge case de normalização. Reaproveita a regex existente
  `extractors.PROCESS_NUMBER_RE`.
- Para os demais comandos, o processo é encontrado entre as assinaturas do próprio chat pelo
  `source` normalizado. Se não for encontrado, a resposta é "você não acompanha" (FR-010,
  SC-006).

## R6 — Pausa por chat e status do processo

- **Decision**:
  - `ProcessSubscription.paused` (por chat). `create_notifications_for_change` ignora assinaturas
    pausadas **em todos os canais**.
  - Novo campo `MonitoredProcess.origin` (`panel` | `telegram`). O bot só altera o `status` de
    processos com `origin=telegram`:
    - sem nenhuma assinatura ativa (`paused=False`) → `PAUSED`;
    - de volta a ter assinatura ativa → `ACTIVE`.
  - Processos cadastrados pelo painel **nunca** têm o status mudado pelo bot. Se um desses
    estiver pausado ou arquivado pelo operador, o `/watch` cria a assinatura e avisa que o
    monitoramento está suspenso pela administração.
- **Rationale**: FR-008 sem regressão. Hoje existem processos do painel sem assinantes que são
  monitorados de propósito, e o bot não pode pausá-los.
- **Alternatives considered**: pausar sempre que não houver assinantes (quebraria processos do
  painel); contar assinaturas "de qualquer canal" (continua sem resolver os processos do painel
  sem assinantes).

## R7 — Mensagens e limites do Telegram

- **Decision**: Texto **puro** (sem `parse_mode`), com `disable_web_page_preview=true`. O
  Telegram já transforma URLs em links. Os alertas reaproveitam
  `notifications.services._build_hybrid_message` no formato compacto (o mesmo do WhatsApp, o
  `else` que não é e-mail). O canal corta em 4096 caracteres e, quando corta, acrescenta
  `… (mensagem cortada) <link do processo>`. Os textos dos comandos ficam centralizados em
  `apps/telegram_bot/messages.py` (Princípio VI).
- **Rationale**: Evita erros de escape de HTML/Markdown com texto que vem do SEI (`<`, `&`, `_`)
  e mantém o texto idêntico entre canais.
- **Anexos**: `sendDocument` com `document=<URL pública>`. O Telegram baixa URLs de até 20 MB,
  que é o mesmo modelo do `send_whatsapp_attachment`. Se falhar, o documento fica pendente para
  retentativa pelo fluxo existente de `NotificationDocumentState`.

## R8 — Grupos

- **Decision**:
  - `TelegramChat.chat_type` ∈ {`private`, `group`, `supergroup`}. Atualizações de `channel` são
    ignoradas.
  - Comandos de gestão (`/watch`, `/unwatch`, `/pause`, `/resume`) em grupo exigem
    `getChatMember(chat_id, from.id).status ∈ {creator, administrator}`. A consulta acontece no
    momento do comando e não é armazenada. Se a chamada falhar, o comando é recusado com
    "não consegui confirmar que você é administrador".
  - `/cmd@OutroBot` é ignorado. `/cmd@NossoBot` é aceito. O username do bot vem de
    `TELEGRAM_BOT_USERNAME` ou, se estiver vazio, de `getMe` (cache em memória do processo).
  - `allowed_updates = ["message", "my_chat_member"]`. Quando o bot sai do grupo
    (`my_chat_member` com `left`/`kicked`) ou o usuário bloqueia o bot (`kicked` no privado),
    o chat vira inalcançável. Quando o bot volta a ser membro, o chat fica alcançável de novo.
  - `message.migrate_to_chat_id`: atualiza o `chat_id` do `TelegramChat` (as assinaturas seguem
    junto, via FK).
- **Privacy mode**: o padrão do BotFather já entrega comandos `/…` em grupos. Não é preciso
  desligá-lo.

## R9 — Envio de notificações fora de ciclos com processos vencidos

- **Finding**: `run_worker._run_cycle` retorna cedo quando não há processos vencidos, então
  `send_pending_notifications()` **só roda quando algum processo estava vencido**. As mudanças
  encontradas por `/check` e as respostas do bot ficariam presas.
- **Decision**: Reordenar `_run_cycle` em três passos:
  1. `process_pending_bot_actions()`;
  2. checagem dos processos vencidos (se houver);
  3. `send_pending_notifications()` **sempre**.
  O custo de uma query de notificações pendentes a cada tick é desprezível.

## R9b — Falhas transitórias no canal

- **Finding**: no pipeline atual, `failed` é **terminal** (`send_pending_notifications` só
  retenta `PENDING`).
- **Decision**: o canal Telegram devolve `pending` para erro de rede, 429 e 5xx, então
  `dispatch_notification` retenta até `MAX_NOTIFICATION_ATTEMPTS` e só então marca `failed`
  (US2 #4). 403 e "chat not found" → `invalid_recipient` + chat inalcançável. Outros 4xx →
  `failed`.

## R9c — Anexos por upload e /ultima (pós-implementação)

- **Finding**: a Bot API só busca por URL arquivos PDF, GIF e ZIP, e as URLs de documento do
  SEI costumam servir HTML ou depender de cabeçalhos. O envio por URL (R7) falharia com
  frequência.
- **Decision**: o Telegram passa a **baixar o arquivo** (`clients.download_document`, a mesma
  função do e-mail) e **fazer upload multipart** (`client.send_document_file`), com limite
  `TELEGRAM_ATTACHMENT_MAX_BYTES` (padrão 20 MB; a Bot API aceita até 50 MB). Falhas de
  download mantêm o documento pendente para retentativa (`NotificationDocumentState`).
  O WhatsApp continua por URL.
- **/ultima**: baixar o documento é acesso ao SEI, então o comando vira
  `BotAction(kind=latest)` executada pelo worker (Princípio I). O protocolo mais recente vem de
  `extractors.latest_protocol_record(process.last_text)`, função agora compartilhada com o botão
  "Enviar última atualização" do painel. O link vem de `DetectedDocument`. Só quando ele é
  desconhecido o worker consulta **uma vez** a página do processo (`get_snapshot` +
  `extract_document_links`). A consulta e o download acontecem uma vez por processo por tick,
  mesmo com vários chats pedindo.

## R10 — Configuração

- **Decision**: As variáveis `TELEGRAM_*` ficam em `config/env_schema.py`. Validação: se
  `TELEGRAM_ENABLED=true`, então `TELEGRAM_BOT_TOKEN` e `TELEGRAM_WEBHOOK_SECRET` são
  obrigatórios, e o secret precisa casar com `^[A-Za-z0-9_-]{16,256}$` (a regra do Telegram
  exige de 1 a 256 caracteres; o mínimo de 16 é nosso, por segurança).
  `TELEGRAM_MAX_PROCESSES_PER_CHAT` tem mínimo 1, e `TELEGRAM_CHECK_COOLDOWN_SECONDS` tem
  mínimo 60.
