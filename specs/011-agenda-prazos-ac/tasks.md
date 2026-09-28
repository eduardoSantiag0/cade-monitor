# Tasks: Agenda e prazos de AC sumário

**Input**: Design documents from `/specs/011-agenda-prazos-ac/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/agenda.md,
quickstart.md

**Tests**: incluídos — Princípio VII / Development Workflow item 2 e 3 da constituição. A
suíte de auto-encerramento (FR-017/FR-018) é tratada com rigor extra: cada guarda de segurança
tem seu próprio teste isolado (nunca um teste combinado que possa mascarar uma guarda quebrada).

**Organization**: tarefas agrupadas por história de usuário (US1/US2/US3 do spec.md), na mesma
ordem de prioridade.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 Criar o app `apps/agenda/` (`__init__.py`, `apps.py` com `AgendaConfig`,
  `migrations/__init__.py`, `tests/__init__.py`, `tests/fixtures/__init__.py` com `load_fixture`
  lendo arquivos de texto — mesmo padrão de `apps/dashboard/tests/fixtures/__init__.py`).
- [ ] T002 Registrar `'apps.agenda.apps.AgendaConfig'` em `INSTALLED_APPS` em `config/settings.py`.
- [ ] T003 [P] Adicionar em `config/env_schema.py`/`config/settings.py` as variáveis
  `AGENDA_CALENDAR_SYNC_INTENSIVE_INTERVAL_SECONDS` (default `86400` — janela intensiva, FR-003),
  `AGENDA_CALENDAR_SYNC_CONFIRMED_INTERVAL_SECONDS` (default `30*86400`),
  `AGENDA_AUTO_CLOSURE_DAYS` (default `10`, FR-017),
  `AGENDA_LAST_CHECK_MAX_AGE_SECONDS` (default `2*86400`, guarda de FR-017d). Documentar no
  `.env.example`.

**Checkpoint**: `python manage.py check` passa; app carrega sem erro.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: modelos, calendário oficial e a fórmula de prazo — base de tudo que segue.

**⚠️ CRITICAL**: nenhuma história de usuário começa antes desta fase terminar.

- [ ] T004 Criar os 3 modelos em `apps/agenda/models.py` conforme data-model.md:
  `CadeCalendarYear`, `CadeCalendarEntry` (`unique_together=('calendar_year','date')`),
  `ProcessInvite` (`unique_together=('process','deadline_type')`).
- [ ] T005 Gerar e revisar a migration: `python manage.py makemigrations agenda`.
- [ ] T006 [P] Registrar os 3 modelos em `apps/agenda/admin.py` (list_display simples).
- [ ] T007 [P] Criar fixture `apps/agenda/tests/fixtures/portaria_feriados_2027.txt` (HTML/texto
  simplificado de um ato oficial de feriados válido — Portaria, órgão competente, Seção 1, ano
  2027, ≥8 datas) e `portaria_invalida.txt` (falha em pelo menos um critério de FR-002, ex. órgão
  errado ou menos de 8 datas).
- [ ] T008 [P] [Foundational] Teste em `apps/agenda/tests/test_calendar_source.py`: parser do ato
  oficial extrai as datas/nomes corretos do fixture válido; `valida_portaria`-equivalente rejeita
  o fixture inválido (cada critério de FR-002 testado: order errado, seção errada, revogado, ano
  fora, poucas datas — um teste por critério).
- [ ] T009 [P] [Foundational] Teste em `apps/agenda/tests/test_calendar_source.py`:
  `sync_calendar_year` grava `CadeCalendarYear(status='confirmed')` + `CadeCalendarEntry`s em
  sucesso; respeita a cadência (`next_check_at`, mock do relógio); falha de rede não lança exceção
  e reagenda `next_check_at`.
- [ ] T010 [P] [Foundational] Teste em `apps/agenda/tests/test_calendar_source.py`:
  `is_business_day` retorna `False` para sábado/domingo e para uma data em `CadeCalendarEntry`;
  `True` para um dia útil comum; ano sem `CadeCalendarYear` confirmado não lança exceção (devolve
  o que souber, conforme contrato).
- [ ] T011 [P] [Foundational] Teste em `apps/agenda/tests/test_deadlines.py`:
  `calcula_prazo_cade` — casos: vencimento preliminar já é dia útil (fica); vencimento preliminar
  cai num feriado cadastrado (empurra para o próximo dia útil); data-evento cai numa sexta antes
  de feriado na segunda (início pula corretamente para o próximo dia útil); ano do calendário não
  confirmado levanta `CalendarNotConfirmedError` (não uma exceção genérica).
- [ ] T012 [Foundational] Implementar `sync_calendar_year`, `is_business_day` em
  `apps/agenda/calendar_source.py` — busca na listagem do DOU (reaproveitando o padrão HTTP de
  `apps/dou/clients.py`, sem duplicar o cliente HTTP: extrair um helper comum se fizer sentido, ou
  replicar o pequeno `_open_request`/`_get` como as features 009/010 já fizeram cada uma a sua
  vez), parsing e validação (FR-002), persistência. *(depende de T004, T008, T009, T010)*
- [ ] T013 [Foundational] Implementar `calcula_prazo_cade` e `CalendarNotConfirmedError` em
  `apps/agenda/deadlines.py`. *(depende de T011)*

**Checkpoint**: `python manage.py test apps.agenda` passa (calendário e fórmula de prazo
testados) antes de iniciar qualquer história de usuário.

---

## Phase 3: User Story 1 - Ver a linha do tempo de prazos de um AC sumário (Priority: P1) 🎯 MVP

**Goal**: a página de um processo AC sumário mostra os prazos calculados a partir dos documentos
e do calendário oficial.

**Independent Test**: fixtures de `last_text` em 4 estágios (só notificação; +edital+publicação;
+aprovação; +certidão) produzem a linha do tempo esperada em cada estágio.

### Tests for User Story 1

- [ ] T014 [P] [US1] Fixtures em `apps/agenda/tests/fixtures/`: `ac_sumario_so_notificacao.txt`,
  `ac_sumario_com_edital.txt`, `ac_sumario_com_aprovacao.txt`, `ac_sumario_com_certidao.txt`
  (cada um com a Lista de Protocolos no formato que `extract_protocol_records` já reconhece, mais
  o rótulo de classificação "Tipo: ... Ato de Concentração Sumário" no cabeçalho), e
  `processo_ordinario.txt` (classificação diferente, para o teste de exclusão).
- [ ] T015 [P] [US1] Teste em `apps/agenda/tests/test_deadlines.py`: `classifica_processo`
  reconhece "Ato de Concentração Sumário" nos fixtures AC sumário; devolve `None` para
  `processo_ordinario.txt` e para cada item da lista de exclusão de FR-005 (ordinário, apuração,
  consulta, recurso — um teste por termo).
- [ ] T016 [P] [US1] Teste em `apps/agenda/tests/test_deadlines.py`: identificação de documentos
  (notificação, edital, publicação, aprovação, certidão) a partir de `extract_protocol_records` —
  cada função de matching (FR-006) testada com um caso positivo e um caso "quase" que não deve
  casar (ex.: despacho decisório NÃO é confundido com despacho de aprovação; despacho ordinatório
  idem; certidão de julgamento NÃO é confundida com certidão de trânsito em julgado).
- [ ] T017 [P] [US1] Teste em `apps/agenda/tests/test_deadlines.py` (fixture
  `ac_sumario_so_notificacao.txt`): `monta_linha_do_tempo` mostra só o prazo de análise da SG
  (FR-007), calculado a partir da data de registro da notificação.
- [ ] T018 [P] [US1] Teste em `apps/agenda/tests/test_deadlines.py` (fixture
  `ac_sumario_com_edital.txt`): a linha do tempo mostra o prazo de análise E o prazo de terceiro
  interessado (FR-008), calculado a partir da publicação do edital.
- [ ] T019 [P] [US1] Teste em `apps/agenda/tests/test_deadlines.py` (fixture
  `ac_sumario_com_aprovacao.txt`): o prazo de análise da SG NÃO aparece mais (FR-007, cumprido);
  o prazo de recurso/avocação aparece (FR-009), calculado a partir da publicação da aprovação; a
  certidão aparece como estimativa (FR-010).
- [ ] T020 [P] [US1] Teste em `apps/agenda/tests/test_deadlines.py` (fixture
  `ac_sumario_com_certidao.txt`): a certidão aparece com a data real do documento, não como
  estimativa (FR-010).
- [ ] T021 [P] [US1] Teste em `apps/agenda/tests/test_deadlines.py`:
  `processo_ordinario.txt` → `monta_linha_do_tempo` devolve lista vazia (FR-005/spec Acceptance
  Scenario 6).
- [ ] T022 [P] [US1] Teste em `apps/agenda/tests/test_deadlines.py`: ano de calendário necessário
  não confirmado (mock) → o prazo correspondente fica ausente da linha do tempo, sem lançar
  exceção (FR-011).
- [ ] T023 [P] [US1] Teste de view: `GET` na página de detalhe de um processo AC sumário (mock de
  `timeline_for_process`) mostra a seção da linha do tempo; processo não-AC-sumário
  (`timeline_for_process` retornando `None`) não mostra a seção, sem erro — no arquivo de teste de
  views já existente do app `processes` (ex. `tests/test_views.py`, mesma convenção da feature
  010).

### Implementation for User Story 1

- [ ] T024 [US1] Implementar `classifica_processo` em `apps/agenda/deadlines.py`, incluindo a
  lista de exclusão de FR-005. *(depende de T015)*
- [ ] T025 [US1] Implementar os 5 matchers de documento (notificação, edital, publicação,
  aprovação, certidão) em `apps/agenda/deadlines.py`, cada um retornando `(documento, confidence)`
  ou `None`, operando sobre a lista de `extract_protocol_records`. *(depende de T016)*
- [ ] T026 [US1] Implementar `monta_linha_do_tempo` em `apps/agenda/deadlines.py`, combinando
  T013 (fórmula), T024 (classificação) e T025 (matchers) conforme FR-007 a FR-011. *(depende de
  T013, T024, T025, T017, T018, T019, T020, T021, T022)*
- [ ] T027 [US1] Implementar `timeline_for_process` em `apps/agenda/selectors.py`. *(depende de
  T026)*
- [ ] T028 [US1] Atualizar a view de detalhe do processo (`apps/processes/views.py`) para incluir
  `timeline_for_process(process)` no contexto, e o template (`templates/processes/detail.html`)
  com a seção condicional. *(depende de T027, T023)*

**Checkpoint**: US1 completo e testável isoladamente — `python manage.py test apps.agenda` cobre
a linha do tempo de ponta a ponta; a página do processo já mostra os prazos.

---

## Phase 4: User Story 2 - Receber convite de calendário (Priority: P2)

**Goal**: assinantes recebem, atualizam e têm cancelados convites `.ics` para os 2 prazos "do
escritório".

**Independent Test**: sequência prazo de análise identificado → cumprido (aprovação) → certidão
prevista → certidão real com data diferente, conferindo REQUEST/CANCEL/REQUEST/REQUEST(seq+1).

### Tests for User Story 2

- [ ] T029 [P] [US2] Teste em `apps/agenda/tests/test_ics.py`: `build_ics` gera um `.ics` válido
  (cabeçalho `BEGIN:VCALENDAR`/`METHOD:REQUEST`, `UID`, `SUMMARY`, data de dia inteiro,
  `TRANSP:TRANSPARENT`); `method='CANCEL'` gera `METHOD:CANCEL`/`STATUS:CANCELLED`; linha maior
  que 75 octetos é dobrada corretamente (RFC 5545).
- [ ] T030 [P] [US2] Teste em `apps/agenda/tests/test_services.py`: prazo de análise identificado
  pela 1ª vez → `refresh_timelines_and_invites` envia 1 e-mail com anexo `.ics` (`method=REQUEST`)
  a cada assinante com e-mail habilitado, e grava `ProcessInvite(status='sent', sequence=0)`.
- [ ] T031 [P] [US2] Teste em `apps/agenda/tests/test_services.py`: chamada seguinte sem mudança
  de data → nenhum e-mail novo (FR-014, idempotência).
- [ ] T032 [P] [US2] Teste em `apps/agenda/tests/test_services.py`: prazo de análise cumprido
  (fixture muda para "com aprovação") → envia CANCEL do convite de análise (FR-016), atualiza
  `ProcessInvite(status='cancelled')`.
- [ ] T033 [P] [US2] Teste em `apps/agenda/tests/test_services.py`: certidão prevista muda de data
  (fixture com previsão diferente) → envia REQUEST atualizado com `sequence` incrementado
  (FR-015).
- [ ] T034 [P] [US2] Teste em `apps/agenda/tests/test_services.py`: assinante com e-mail
  desabilitado ou assinatura pausada não recebe nenhum convite (FR-013, mesma regra de
  `Subscriber.is_reachable()`/`ProcessSubscription.paused` já usada em outras features).

### Implementation for User Story 2

- [ ] T035 [US2] Implementar `build_ics` em `apps/agenda/ics.py` (RFC 5545 mínimo, ver
  research.md). *(depende de T029)*
- [ ] T036 [US2] Adicionar suporte a `content_type` com parâmetro extra (ex.
  `text/calendar; method=REQUEST`) no anexo de `apps/notifications/channels/email.py` — confirmar
  que o valor passa direto para `msg.attach(...)` sem normalização que quebre o `; method=`.
- [ ] T037 [US2] Implementar `refresh_timelines_and_invites` em `apps/agenda/services.py`:
  itera processos AC sumário ativos, monta a linha do tempo (T026), compara com `ProcessInvite`
  existente para os 2 tipos com convite, decide REQUEST novo/atualizado/CANCEL/nada, envia via
  `send_email_notification` (T036) a cada assinante elegível, grava `ProcessInvite`. Nunca lança
  exceção para o chamador. *(depende de T026, T035, T036, T030, T031, T032, T033, T034)*
- [ ] T038 [US2] Integrar `sync_calendar` e `refresh_timelines_and_invites` em
  `apps/monitoring/management/commands/run_worker.py::_run_cycle`, nessa ordem, mesmo padrão
  try/except + log das features 009/010. *(depende de T012, T037)*

**Checkpoint**: US2 completo — convites funcionando de ponta a ponta, sem afetar US1.

---

## Phase 5: User Story 3 - Auto-encerramento (Priority: P3)

**Goal**: processo com certidão + 10 dias sem movimentação é apagado, só quando as 4 guardas de
segurança passam.

**Independent Test**: os 6 cenários de Acceptance Scenarios da História 3 (apaga; não apaga por
estar dentro da janela; não apaga por movimentação nova; não apaga por erro na verificação; não
apaga por verificação desatualizada; não apaga por confiança baixa), cada um isolado.

### Tests for User Story 3

- [ ] T039 [P] [US3] Teste em `apps/agenda/tests/test_services.py`: certidão de confiança alta há
  11 dias, sem `DetectedChange` desde então, `last_error=''`, `last_checked_at` recente →
  `run_auto_closure` apaga o processo (Acceptance Scenario 1) e loga os critérios (FR-020, mock
  de logger/verificação de chamada).
- [ ] T040 [P] [US3] Teste em `apps/agenda/tests/test_services.py`: certidão há 5 dias → processo
  NÃO é apagado (Scenario 2).
- [ ] T041 [P] [US3] Teste em `apps/agenda/tests/test_services.py`: certidão há 15 dias, mas
  `DetectedChange` há 3 dias (posterior à certidão) → processo NÃO é apagado, contagem reiniciada
  (Scenario 3).
- [ ] T042 [P] [US3] Teste em `apps/agenda/tests/test_services.py`: certidão há 15 dias sem
  movimentação, mas `last_error` não vazio → processo NÃO é apagado (Scenario 4).
- [ ] T043 [P] [US3] Teste em `apps/agenda/tests/test_services.py`: mesmo cenário, mas
  `last_checked_at` há mais de `AGENDA_LAST_CHECK_MAX_AGE_SECONDS` → processo NÃO é apagado
  (Scenario 5).
- [ ] T044 [P] [US3] Teste em `apps/agenda/tests/test_services.py`: mesmo cenário, mas a certidão
  identificada tem confiança baixa → processo NÃO é apagado (Scenario 6).
- [ ] T045 [P] [US3] Teste em `apps/agenda/tests/test_services.py`: processo com `ProcessInvite`
  pendente é apagado (cenário 1) → um e-mail de CANCEL é enviado antes/durante o apagamento
  (FR-019), verificável pelo mock de `send_email_notification` sendo chamado antes da exclusão do
  registro no banco.
- [ ] T046 [P] [US3] Teste em `apps/agenda/tests/test_services.py`: `run_auto_closure` sobre um
  processo que não é AC sumário, ou sem certidão nenhuma, não faz nada (sem erro).

### Implementation for User Story 3

- [ ] T047 [US3] Implementar `run_auto_closure` em `apps/agenda/services.py`: as 4 guardas de
  FR-017 como condições explícitas e nomeadas (não um único `if` opaco — cada guarda deve ser
  legível e testável em isolamento), cancelamento de convites pendentes (T035/T037) antes do
  apagamento, log estruturado dos critérios (FR-020), `process.delete()` (cascata cobre
  `ProcessSubscription`/documentos ligados). Nunca lança exceção para o chamador. *(depende de
  T026, T037, T039-T046)*
- [ ] T048 [US3] Integrar `run_auto_closure` em `_run_cycle`, por último no bloco da feature 011
  (depois de `refresh_timelines_and_invites`, conforme contracts/agenda.md). *(depende de T047)*

**Checkpoint**: US3 completo — auto-encerramento funcionando com todas as guardas de segurança
testadas isoladamente.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T049 Rodar `python manage.py test apps.agenda apps.processes apps.monitoring` e confirmar
  toda a suíte (existente + nova) passando (quickstart.md, passo 1).
- [ ] T050 Validar manualmente contra a fonte real do calendário oficial seguindo quickstart.md
  passo 3 (1-2 chamadas reais — nunca em loop). Documentar qualquer divergência em research.md,
  "Correção pós-implementação", seguindo o modelo das features 008/009/010.
- [ ] T051 Validar manualmente a extração de classificação (quickstart.md passo 4) contra pelo
  menos um processo real conhecido como AC sumário, se houver algum já cadastrado no sistema;
  documentar o formato real do rótulo "Tipo:" encontrado, ajustando `classifica_processo` se
  necessário.
- [ ] T052 [P] Revisão final de segurança do auto-encerramento: reler FR-017/FR-018/T047 e
  confirmar, por inspeção de código (não só teste), que as 4 guardas usam `and` explícito (nunca
  uma condição que, ausente por bug, falhe "aberta" para o lado do apagamento).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências.
- **Foundational (Phase 2)**: depende do Setup; bloqueia todas as histórias.
- **User Story 1 (Phase 3)**: depende só da Foundational — pode ser entregue sozinha como MVP
  (linha do tempo visível, sem convite nem auto-encerramento).
- **User Story 2 (Phase 4)**: depende de US1 (T026, a linha do tempo é o que decide o que
  convidar).
- **User Story 3 (Phase 5)**: depende de US1 (T026, identifica a certidão) e de US2 (T037, precisa
  cancelar convite antes de apagar — FR-019).
- **Polish (Phase 6)**: depende de todas as histórias desejadas estarem completas.

### Parallel Opportunities

- T003 (Setup) pode rodar em paralelo com T001/T002.
- Dentro da Foundational: T006-T011 podem rodar em paralelo entre si depois de T004/T005.
- Todos os testes marcados `[P]` de uma mesma história podem ser escritos em paralelo entre si
  (T014-T023, T029-T034, T039-T046).
- US2 e US3 NÃO podem ser paralelizadas de verdade apesar de serem histórias separadas — US3
  depende diretamente de uma função de US2 (cancelamento de convite antes de apagar).

---

## Implementation Strategy

### MVP First (User Story 1)

1. Completar Setup (T001-T003) e Foundational (T004-T013).
2. Completar User Story 1 (T014-T028).
3. Rodar `python manage.py test apps.agenda` e validar quickstart.md passos 1-2.
4. Esse já é o ganho mais caro (spec.md: User Story 1 é P1 — visibilidade dos prazos é o valor
   central; convite e auto-encerramento são incrementos).

### Incremental Delivery

1. Setup + Foundational → calendário e fórmula de prazo prontos.
2. US1 → linha do tempo visível na página do processo (MVP).
3. US2 → convites de calendário para os prazos do escritório.
4. US3 → auto-encerramento, com todas as guardas de segurança testadas — **não pular a checagem
   T052 antes de considerar esta fase pronta**, dado o caráter irreversível.
5. Polish → suíte completa + validação ao vivo (calendário e classificação) + revisão de
   segurança.

---

## Notes

- Nenhuma dependência nova de runtime (Princípio VIII); `.ics` gerado por template de texto puro.
- `sync_calendar`, `refresh_timelines_and_invites` e `run_auto_closure` nunca lançam exceção para
  `run_worker` (mesma garantia das features 009/010).
- FR-017/FR-018 (auto-encerramento) são a única ação destrutiva desta feature — tratados com
  testes isolados por guarda (T039-T046) e uma revisão de código dedicada (T052), não só
  cobertura de teste.
- Parar em qualquer checkpoint acima já entrega valor de forma independente e testável — US1
  sozinha (linha do tempo) já é um produto completo se o dono do projeto preferir adiar US2/US3.
