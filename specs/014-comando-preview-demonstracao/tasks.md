# Tasks: Comando /preview — demonstração para portfólio

**Input**: Design documents from `/specs/014-comando-preview-demonstracao/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/preview.md,
quickstart.md

**Tests**: incluídos — Princípio VII / Development Workflow item 2 da constituição.

**Organization**: User Story 1 (ver a demonstração) e User Story 2 (garantia de nunca tocar dado
real) são tratadas juntas como um único MVP P1 — a segunda não é um incremento sobre a primeira,
é uma exigência de segurança da mesma entrega (por decisão explícita desta rodada de tasks).
User Story 3 (README) vem depois.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Criar `apps/telegram_bot/demo.py` com as constantes do cenário fixo:
  `DEMO_PROCESS_SOURCE = '08700.000000/2026-00'`, `DEMO_PROCESS_LABEL`, `DEMO_OLD_TEXT`,
  `DEMO_NEW_TEXT` (andamento anterior/novo, textos fictícios em português).
- [X] T002 [P] Criar `apps/telegram_bot/tests/test_demo.py` (esqueleto, sem teste ainda).

**Checkpoint**: `python manage.py check` passa; módulo importa sem erro.

---

## Phase 2: User Story 1+2 - Demonstração completa, sem tocar dado real (Priority: P1) 🎯 MVP

**Goal**: `/preview` responde com uma demonstração completa do fluxo principal, reaproveitando
`compute_diff`/`build_test_notification_body`, sem nenhuma chamada de rede, sem envio real de
notificação, sem afetar processos/assinantes reais.

**Independent Test**: chamar `RunDemoUseCase().run()` diretamente (sem subir o bot) com mock
estrito de qualquer função de rede/envio, e confirmar que a resposta contém todos os elementos de
FR-009 e que nenhum mock de rede/envio foi chamado.

### Tests for User Story 1+2

- [X] T003 [P] [US1] Teste em `apps/telegram_bot/tests/test_demo.py`: `RunDemoUseCase().run()`
  devolve uma string contendo processo fictício (rotulado como demonstração), andamento anterior,
  nova movimentação, resumo (derivado de `compute_diff`, não hardcoded), data/hora, e os 3 canais
  de notificação (FR-009).
- [X] T004 [P] [US2] Teste em `apps/telegram_bot/tests/test_demo.py` (mock estrito de rede):
  `unittest.mock.patch('urllib.request.urlopen')` configurado para levantar exceção se chamado;
  `RunDemoUseCase().run()` completa normalmente sem disparar essa exceção (prova estrutural de
  FR-006/SC-002 — nenhuma função de rede é alcançada, direta ou indiretamente).
- [X] T005 [P] [US2] Teste em `apps/telegram_bot/tests/test_demo.py` (mock estrito de envio):
  `unittest.mock.patch` em `apps.notifications.channels.email.send_email_notification`,
  `apps.notifications.channels.evolution.send_whatsapp_notification`, e
  `apps.telegram_bot.client.send_message`/`call`, cada um configurado para levantar exceção se
  chamado; `RunDemoUseCase().run()` completa normalmente (prova de FR-007/SC-003 — o conteúdo de
  notificação é só formatado e exibido, nunca despachado).
- [X] T006 [P] [US2] Teste em `apps/telegram_bot/tests/test_demo.py`: chamar
  `RunDemoUseCase().run()` 5 vezes seguidas; confirmar `MonitoredProcess.objects.filter(source=
  DEMO_PROCESS_SOURCE).count() == 1` e `DetectedChange.objects.filter(process__source=
  DEMO_PROCESS_SOURCE).count() == 1` ao final (FR-002/SC-004 — idempotente, nunca acumula).
- [X] T007 [P] [US2] Teste em `apps/telegram_bot/tests/test_demo.py`: depois de
  `RunDemoUseCase().run()`, `apps.monitoring.scheduler.get_due_processes()` nunca inclui o
  processo de demonstração (confirma `status=ARCHIVED` isola do ciclo real — FR-008).
- [X] T008 [P] [US1] Teste em `apps/telegram_bot/tests/test_services.py` (arquivo já existente):
  `/preview` está registrado em `COMMANDS`, NÃO está em `MANAGEMENT_COMMANDS`, e
  `cmd_preview(chat, '')` funciona tanto simulando um chat privado quanto um chat de grupo, sem
  exigir assinatura/processo prévio do usuário (spec.md, US1 cenário 3).

### Implementation for User Story 1+2

- [X] T009 [US1] Implementar `_get_or_create_demo_process()` em `apps/telegram_bot/demo.py`:
  get-or-create de `MonitoredProcess(source=DEMO_PROCESS_SOURCE, status=ProcessStatus.ARCHIVED,
  label=DEMO_PROCESS_LABEL)`. *(depende de T001)*
- [X] T010 [US1] Implementar `_get_or_create_demo_change(process, summary, diff_text)` em
  `apps/telegram_bot/demo.py`: get-or-create/atualiza no lugar o conjunto reservado
  `CheckRun`/`PageSnapshot`/`DetectedChange` de demonstração (nunca cria um segundo conjunto —
  reaproveita os mesmos registros a cada chamada). *(depende de T006, T009)*
- [X] T011 [US1] Implementar `demo_preview(process, old_text, new_text, summary, detected_at,
  notification_excerpt)` em `apps/telegram_bot/messages.py`: monta o texto final da resposta,
  combinando todos os elementos de FR-009, claramente rotulado como demonstração.
- [X] T012 [US1] Implementar `RunDemoUseCase.run()` em `apps/telegram_bot/demo.py`, conforme
  contracts/preview.md: chama T009 → monta cenário fixo → `compute_diff` (`apps.monitoring.diff`)
  → T010 → `build_test_notification_body` (`apps.notifications.services`) → T011. Nunca chama
  `get_snapshot`, `collect_new_documents`, `create_notifications_for_change`, nem qualquer função
  de envio real. *(depende de T003, T004, T005, T010, T011)*
- [X] T013 [US1] Implementar `cmd_preview(chat, args)` em `apps/telegram_bot/services.py`
  (handler fino: só chama `RunDemoUseCase().run()`) e registrar `COMMANDS['preview'] = cmd_preview`
  — fora de `MANAGEMENT_COMMANDS`. *(depende de T008, T012)*
- [X] T014 [US1] Adicionar `('preview', '🧪 Ver uma demonstração do sistema')` a `BOT_COMMANDS` em
  `apps/telegram_bot/client.py` (alimenta `set_my_commands()`, publicado a cada início do
  `run_worker`).

**Checkpoint**: US1+US2 completo — `/preview` funciona de ponta a ponta, com as garantias de
segurança provadas por teste, não só por inspeção.

---

## Phase 3: User Story 3 - README explica o modo de demonstração (Priority: P2)

**Goal**: quem chega ao repositório entende, pelo README, o que `/preview` faz e como executá-lo.

**Independent Test**: ler só a seção nova do README e explicar, com as próprias palavras, o que o
`/preview` demonstra.

### Implementation for User Story 3

- [X] T015 [US3] Adicionar ao README uma seção "Modo de demonstração" explicando o propósito
  (portfólio, sem configurar nada real), como executar `/preview`, e um exemplo do formato de
  resposta (FR-011).

**Checkpoint**: US3 completo — README explica a feature sem exigir contexto prévio.

---

## Phase 4: Polish & Cross-Cutting Concerns

- [X] T016 Rodar `./.venv/Scripts/python.exe manage.py test apps.telegram_bot` e confirmar toda a
  suíte (existente + nova) passando (quickstart.md, passo 1).
- [X] T017 Validar quickstart.md passos 2-4 (resposta manual, idempotência, suíte completa do
  bot).
- [X] T018 Revisão dedicada confirmando FR-006/FR-007 por inspeção direta de
  `apps/telegram_bot/demo.py`: `RunDemoUseCase.run()` nunca importa/chama, direta ou
  indiretamente, `apps.monitoring.clients.get_snapshot`/`collect_new_documents`, nem qualquer
  função de `apps.notifications.channels.*`/`apps.telegram_bot.client.call`/`send_message` fora
  do próprio handler que devolve a resposta — mesmo espírito da revisão de segurança da feature
  011, adaptado ao risco desta spec (vazamento de I/O real, não ação destrutiva).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências.
- **User Story 1+2 (Phase 2)**: depende do Setup — MVP, entrega P1 completa (funcionalidade +
  garantias de segurança juntas, por decisão desta rodada).
- **User Story 3 (Phase 3)**: independente de US1+US2 no código (só documentação), mas
  logicamente vem depois (documenta o que já existe).
- **Polish (Phase 4)**: depende de todas as histórias desejadas estarem completas.

### Parallel Opportunities

- T001/T002 (Setup) podem rodar em paralelo.
- Todos os testes `[P]` de US1+US2 (T003-T008) podem ser escritos em paralelo entre si.
- T015 (US3) pode ser escrita em paralelo com qualquer tarefa de implementação de US1+US2, já que
  não depende de código, só da spec.

---

## Implementation Strategy

### MVP First (User Story 1+2)

1. Completar Setup (T001-T002).
2. Completar User Story 1+2 (T003-T014) — funcionalidade e segurança juntas, sem separação.
3. Rodar `./.venv/Scripts/python.exe manage.py test apps.telegram_bot` e validar quickstart.md
   passos 1-3.
4. Essa já é a entrega completa do ponto de vista de produto — US3 é só documentação.

### Incremental Delivery

1. Setup → módulo `demo.py` pronto para receber a lógica.
2. US1+US2 → `/preview` funcionando de ponta a ponta, com garantias de segurança testadas (MVP).
3. US3 → README explica a feature.
4. Polish → suíte completa + revisão de segurança dedicada.

---

## Notes

- Nenhuma dependência nova (Princípio VIII); nenhuma migration nova (reaproveita modelos
  existentes sem alteração de schema).
- `RunDemoUseCase.run()` nunca lança exceção não tratada para o chamador — comando síncrono no
  webhook, mesmo padrão de robustez das features anteriores.
- Parar no checkpoint de US1+US2 já entrega o valor completo de produto — US3 é só polimento de
  descoberta (README), não uma dependência funcional.

**Desvio de execução**: os testes de `telegram_bot` neste repositório vivem em `tests/` na raiz
(não em `apps/telegram_bot/tests/`, que não existia antes desta feature) — `T003`-`T007` foram
implementados em `tests/test_telegram_demo.py` e `T008` em `tests/test_telegram_commands.py`
(nova classe `PreviewCommandTest`), seguindo a convenção já estabelecida pelo resto do app em vez
do caminho literal sugerido originalmente.
