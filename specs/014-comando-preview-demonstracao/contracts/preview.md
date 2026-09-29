# Contrato: `apps/telegram_bot/demo.py` — RunDemoUseCase

Módulo interno ao monolito. Único consumidor: `apps/telegram_bot/services.py::cmd_preview`.

## `RunDemoUseCase`

### `RunDemoUseCase.run() -> str`

- **Passo 1**: `_get_or_create_demo_process()` — get-or-create do `MonitoredProcess` fictício
  (`source=DEMO_PROCESS_SOURCE`, `status=ProcessStatus.ARCHIVED`). Nunca faz requisição de rede.
- **Passo 2**: monta o cenário fixo: `OLD_TEXT`/`NEW_TEXT` (constantes do módulo — textos de
  andamento fictícios, ex. "Processo distribuído" → "+ Documento adicionado aos autos").
- **Passo 3**: `compute_diff(OLD_TEXT, NEW_TEXT)` (`apps.monitoring.diff`, função pura, já
  existente) → `(summary, diff_text)`.
- **Passo 4**: `_get_or_create_demo_change(process, summary, diff_text)` — get-or-create/atualiza
  no lugar o `CheckRun`/`PageSnapshot`/`DetectedChange` reservados de demonstração (mesmos modelos
  reais, nunca um segundo conjunto).
- **Passo 5**: `build_test_notification_body(process.label, process.effective_url, channel='telegram')`
  (`apps.notifications.services`, já existente) → texto de exemplo de notificação.
- **Passo 6**: monta e retorna o texto final da resposta do Telegram (template em
  `apps/telegram_bot/messages.py::demo_preview`), combinando: rótulo de demonstração, processo
  fictício, andamento anterior, nova movimentação, data/hora atual, `summary` (passo 3), lista de
  canais (`📧 E-mail`, `📱 WhatsApp`, `🤖 Telegram` — os três canais já suportados pelo sistema),
  e um trecho do exemplo de notificação (passo 5).
- **Garantias**: nunca chama `get_snapshot`, `collect_new_documents`,
  `create_notifications_for_change`, nem qualquer função de `apps.notifications.channels.*` (envio
  real). Nunca lança exceção para o chamador de forma não tratada — qualquer erro inesperado vira
  uma resposta de erro genérica (mesmo padrão de robustez das features anteriores), já que é um
  comando síncrono no webhook.

## `apps/telegram_bot/services.py`

### `cmd_preview(chat: TelegramChat, args: str) -> str`

- Handler fino: `return RunDemoUseCase().run()`. Nenhuma lógica de negócio aqui (Princípio III).
- Registrado em `COMMANDS['preview'] = cmd_preview`, **fora** de `MANAGEMENT_COMMANDS` (research.md
  — sem restrição de administrador em grupo).

## `apps/telegram_bot/client.py`

- `BOT_COMMANDS` ganha `('preview', '🧪 Ver uma demonstração do sistema')`, na lista que alimenta
  `set_my_commands()` (menu de comandos do bot, já publicado a cada início do `run_worker`).
