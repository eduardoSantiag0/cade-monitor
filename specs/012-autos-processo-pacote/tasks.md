# Tasks: Pacote de autos (documentos públicos) do processo

**Input**: Design documents from `/specs/012-autos-processo-pacote/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/autos.md, quickstart.md

**Tests**: incluídos — Princípio VII / Development Workflow item 2 e 3 da constituição.

**Organization**: tarefas agrupadas por história de usuário (US1/US2/US3 do spec.md), na mesma
ordem de prioridade.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 Criar o app `apps/autos/` (`__init__.py`, `apps.py` com `AutosConfig`,
  `migrations/__init__.py`, `tests/__init__.py`, `tests/fixtures/__init__.py` com `load_fixture`
  — mesmo padrão de `apps/dashboard/tests/fixtures/__init__.py`).
- [ ] T002 Registrar `'apps.autos.apps.AutosConfig'` em `INSTALLED_APPS` em `config/settings.py`.
- [ ] T003 [P] Confirmar/configurar `MEDIA_ROOT`/`MEDIA_URL` em `config/settings.py` (se ainda não
  existir um diretório de mídia gravável configurado) — é onde os ZIPs prontos ficam.
- [ ] T004 [P] Adicionar em `config/env_schema.py`/`config/settings.py`:
  `AUTOS_PACKAGE_TTL_SECONDS` (default `7*86400` — 7 dias) e
  `AUTOS_MAX_DOCUMENTS_PER_TICK` (default `1`, nº de documentos processados por chamada de
  `run_pending_packages` dentro de um ciclo do worker — evita que um pacote grande monopolize
  ciclos inteiros do worker). Documentar no `.env.example`.

**Checkpoint**: `python manage.py check` passa; app carrega sem erro.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: modelo, admin e seletor — base de tudo que segue.

**⚠️ CRITICAL**: nenhuma história de usuário começa antes desta fase terminar.

- [ ] T005 Criar `AutosPackageJob` em `apps/autos/models.py` conforme data-model.md (`status`
  choices `queued`/`processing`/`ready`/`failed`/`expired`; FKs `process`/`requested_by`).
- [ ] T006 Gerar e revisar a migration: `python manage.py makemigrations autos`.
- [ ] T007 [P] Registrar `AutosPackageJob` em `apps/autos/admin.py` (list_display simples,
  filtro por `status`).
- [ ] T008 [P] Criar `apps/autos/selectors.py::active_or_recent_job(process) -> AutosPackageJob |
  None` (job `queued`/`processing`, ou `ready` com `expires_at` no futuro).
- [ ] T009 [P] Teste em `apps/autos/tests/test_selectors.py`: `active_or_recent_job` encontra um
  job `queued`/`processing`; encontra um `ready` não expirado; devolve `None` para `ready` expirado
  e para `failed`.

**Checkpoint**: `./.venv/Scripts/python.exe manage.py test apps.autos` passa (modelo, admin, seletor
testados) antes de iniciar qualquer história de usuário.

---

## Phase 3: User Story 1 - Baixar o pacote completo (Priority: P1) 🎯 MVP

**Goal**: usuário pede a montagem, acompanha o status, e baixa o ZIP pronto quando todos os
documentos têm link público (caminho feliz, sem indisponíveis).

**Independent Test**: fixture de processo com N documentos todos com link → job processado pelo
worker chega a `ready`, ZIP final com N entradas numeradas na ordem correta.

### Tests for User Story 1

- [ ] T010 [P] [US1] Fixture em `apps/autos/tests/fixtures/`: `processo_todos_com_link.txt`
  (texto normalizado simulando a Lista de Protocolos, 5 documentos) e o HTML correspondente
  `processo_todos_com_link.html` (com os `<a href>` de download de cada um, para
  `extract_document_links`).
- [ ] T011 [P] [US1] Teste em `apps/autos/tests/test_builder.py`: `monta_pacote` sobre o fixture
  T010 (mock de `get_snapshot` e `download_document`) produz um ZIP com 5 entradas nomeadas "1. ...
  " a "5. ...", na ordem da Lista de Protocolos; `job.status` termina `ready`,
  `job.total_declared == job.total_processed == 5`.
- [ ] T012 [P] [US1] Teste em `apps/autos/tests/test_builder.py`: `monta_pacote` aplica
  `time.sleep(settings.SLEEP_BETWEEN_REQUESTS_SECONDS)` entre cada download (mock de `time.sleep`,
  confere número de chamadas).
- [ ] T013 [P] [US1] Teste em `apps/autos/tests/test_services.py`: `request_package` cria um
  `AutosPackageJob(status='queued')` quando não há job ativo/recente para o processo.
- [ ] T014 [P] [US1] Teste em `apps/autos/tests/test_services.py`: `request_package` reaproveita
  (não cria um segundo) quando já existe um job `queued`/`processing`/`ready`-não-expirado para o
  mesmo processo (FR-005/SC-004).
- [ ] T015 [P] [US1] Teste em `apps/autos/tests/test_services.py`: `run_pending_packages` pega o
  job `queued` mais antigo, marca `processing`, chama `monta_pacote` (mock), e nunca lança exceção
  para o chamador mesmo se `monta_pacote` levantar um erro inesperado (vira `status='failed'`).
- [ ] T016 [P] [US1] Teste de view em `apps/autos/tests/test_views.py`: `POST` no endpoint de
  pedido sem estar autenticado → redireciona para login (FR-006); autenticado → cria/reaproveita o
  job e redireciona para a página do processo.
- [ ] T017 [P] [US1] Teste de view em `apps/autos/tests/test_views.py`: `GET` no endpoint de
  download com `job.status != 'ready'` ou `expires_at` no passado → 404; com `status='ready'` e
  não expirado → `FileResponse` com o conteúdo do ZIP.

### Implementation for User Story 1

- [ ] T018 [US1] Implementar `monta_pacote(job, timeout, user_agent)` em `apps/autos/builder.py`
  para o caminho feliz (todos os documentos com link): `get_snapshot` → `extract_protocol_records`
  + `extract_document_links` → loop com `download_document` + pausa → escreve ZIP em streaming
  para `MEDIA_ROOT` → `job.status='ready'`, `file_path`, `expires_at`. *(depende de T011, T012)*
- [ ] T019 [US1] Implementar `request_package(process, user)` e `run_pending_packages(now)` em
  `apps/autos/services.py`, usando `active_or_recent_job` (T008). *(depende de T013, T014, T015)*
- [ ] T020 [US1] Implementar as views em `apps/autos/views.py` (pedir, baixar — `@login_required`)
  e `apps/autos/urls.py`; incluir em `apps/processes/urls.py` (`<int:pk>/autos/pedir/`,
  `<int:pk>/autos/baixar/<int:job_id>/`). *(depende de T016, T017, T019)*
- [ ] T021 [US1] Atualizar `apps/processes/views.py::process_detail` para incluir
  `active_or_recent_job(process)` no contexto, e `templates/processes/detail.html` com a seção
  "Autos" (botão de pedir, status, link de download quando pronto).
- [ ] T022 [US1] Integrar `run_pending_packages` em
  `apps/monitoring/management/commands/run_worker.py::_run_cycle`, mesmo padrão try/except + log
  das features 009/010/011. *(depende de T019)*

**Checkpoint**: US1 completo e testável isoladamente — pedido → processamento em segundo plano →
download funcionando de ponta a ponta para o caminho feliz.

---

## Phase 4: User Story 2 - Placeholder corroborado para documento indisponível (Priority: P2)

**Goal**: documento sem link (ou cujo download falhou) vira um `.txt` numerado explicando o
motivo, quando há corroboração no processo já extraído — sem derrubar o pacote.

**Independent Test**: fixture com 5 documentos, o 3º sem link mas com um andamento explicando
("documento restrito") → ZIP final com 5 entradas, a 3ª sendo o `.txt` do motivo.

### Tests for User Story 2

- [ ] T023 [P] [US2] Fixture em `apps/autos/tests/fixtures/`: `processo_um_indisponivel.txt` +
  `.html` (5 documentos, o 3º sem `<a href>` de download, andamento com texto "documento restrito"
  citando o número desse documento).
- [ ] T024 [P] [US2] Teste em `apps/autos/tests/test_builder.py`: `monta_pacote` sobre o fixture
  T023 produz 5 entradas (4 reais + 1 `.txt` na 3ª posição, com o texto do motivo declarado);
  `job.status='ready'`.
- [ ] T025 [P] [US2] Teste em `apps/autos/tests/test_builder.py`: documento COM link, mas
  `download_document` levanta erro (mock de falha de rede) e há corroboração no andamento → mesma
  regra do T024 (vira placeholder, não derruba o job) — spec.md Edge Cases.
- [ ] T026 [P] [US2] Teste em `apps/autos/tests/test_builder.py`: motivo declarado no PRÓPRIO texto
  da Lista de Protocolos (não só no andamento) também corrobora — ex. quando o SEI já anota
  "documento sigiloso" na própria linha do protocolo.

### Implementation for User Story 2

- [ ] T027 [US2] Implementar a busca de corroboração (andamento via `extract_movement_records` +
  texto da própria Lista de Protocolos) em `apps/autos/builder.py`, e o caminho de escrita do
  placeholder `.txt` numerado quando corroborado. *(depende de T024, T025, T026)*

**Checkpoint**: US2 completo — documentos indisponíveis com motivo declarado não impedem mais o
pacote de ficar pronto.

---

## Phase 5: User Story 3 - Integridade acima de completude forçada (Priority: P3)

**Goal**: quando um documento falta sem nenhuma corroboração, o pacote inteiro falha com mensagem
clara, sem entregar ZIP parcial; nova tentativa é sempre permitida depois.

**Independent Test**: fixture com 5 documentos, o 4º sem link e sem nenhuma corroboração → job
`failed`, nenhum arquivo em `MEDIA_ROOT`, pedido seguinte cria um novo job normalmente.

### Tests for User Story 3

- [ ] T028 [P] [US3] Fixture em `apps/autos/tests/fixtures/`: `processo_divergencia.txt` + `.html`
  (5 documentos, o 4º sem link e sem qualquer menção corroborando o motivo em andamento ou na
  própria lista).
- [ ] T029 [P] [US3] Teste em `apps/autos/tests/test_builder.py`: `monta_pacote` sobre o fixture
  T028 termina com `job.status='failed'`, `job.error` citando a divergência (nº do documento/
  posição), e nenhum arquivo ZIP escrito em `MEDIA_ROOT` (verificar que o arquivo parcial é
  descartado, não só que `file_path` fica vazio).
- [ ] T030 [P] [US3] Teste em `apps/autos/tests/test_services.py`: depois de um job `failed`,
  `request_package` para o mesmo processo cria um NOVO job `queued` normalmente (FR-010 — falha
  anterior não bloqueia).
- [ ] T031 [P] [US3] Teste em `apps/autos/tests/test_services.py`: `run_pending_packages` expira
  (remove o arquivo + marca `status='expired'`) um job `ready` cujo `expires_at` já passou
  (FR-011), sem afetar jobs `ready` ainda válidos.
- [ ] T032 [P] [US3] Teste de view em `apps/autos/tests/test_views.py`: download de um job
  `expired`/`failed` → 404 (mesma regra de T017, agora cobrindo os dois status adicionais).

### Implementation for User Story 3

- [ ] T033 [US3] Implementar a checagem final de integridade em `apps/autos/builder.py`: ao
  encontrar qualquer registro sem corroboração (T027 não achou motivo), registrar a divergência;
  ao final, se houve alguma divergência, descartar o arquivo ZIP parcial (nunca deixar em
  `MEDIA_ROOT` acessível) e marcar `job.status='failed'` com `job.error` legível. *(depende de
  T029)*
- [ ] T034 [US3] Implementar a expiração/limpeza de jobs `ready` vencidos dentro de
  `run_pending_packages` (`apps/autos/services.py`). *(depende de T031)*

**Checkpoint**: US3 completo — a rede de segurança de integridade está no lugar, com teste
cobrindo o descarte do arquivo parcial e a expiração de pacotes antigos.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T035 Rodar `./.venv/Scripts/python.exe manage.py test apps.autos apps.monitoring
  apps.processes` e confirmar toda a suíte (existente + nova) passando (quickstart.md, passo 1).
- [ ] T036 Validar manualmente contra um processo público real seguindo quickstart.md passo 3
  (1-2 chamadas reais — nunca em loop). Documentar qualquer divergência entre o formato real e o
  assumido em `builder.py`/`extract_document_links` numa seção "Correção pós-implementação" em
  research.md, seguindo o modelo das features 008-011; ajustar se necessário.
- [ ] T037 [P] Revisar `.env.example` e a seção do README sobre o worker para mencionar as novas
  variáveis `AUTOS_*` (T004) e a nova seção "Autos" da página do processo.
- [ ] T038 [P] Confirmar que `MEDIA_ROOT` está fora do controle de versão (`.gitignore`) e que o
  Docker Compose/deploy tem um volume persistente para ele, se aplicável ao ambiente de produção
  já configurado (revisão de infraestrutura, não código novo).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências.
- **Foundational (Phase 2)**: depende do Setup; bloqueia todas as histórias.
- **User Story 1 (Phase 3)**: depende só da Foundational — pode ser entregue sozinha como MVP
  (processos onde todo documento tem link já funcionam de ponta a ponta).
- **User Story 2 (Phase 4)**: depende de US1 (T018, é uma extensão de `monta_pacote`).
- **User Story 3 (Phase 5)**: depende de US2 (T027, a checagem de integridade precisa saber
  quando algo NÃO foi corroborado, que é exatamente o que US2 introduz).
- **Polish (Phase 6)**: depende de todas as histórias desejadas estarem completas.

### Parallel Opportunities

- T003/T004 (Setup) podem rodar em paralelo com T001/T002.
- Dentro da Foundational: T007-T009 podem rodar em paralelo entre si depois de T005/T006.
- Todos os testes `[P]` de uma mesma história podem ser escritos em paralelo entre si
  (T010-T017, T023-T026, T028-T032).
- US2 e US3 não podem ser paralelizadas de verdade (US3 depende diretamente da lógica de
  corroboração que US2 introduz em `builder.py`).

---

## Implementation Strategy

### MVP First (User Story 1)

1. Completar Setup (T001-T004) e Foundational (T005-T009).
2. Completar User Story 1 (T010-T022).
3. Rodar `./.venv/Scripts/python.exe manage.py test apps.autos` e validar quickstart.md passos 1-2.
4. Esse já é o ganho mais caro (spec.md: User Story 1 é P1 — processos sem documento restrito já
   funcionam de ponta a ponta).

### Incremental Delivery

1. Setup + Foundational → modelo, admin, seletor prontos.
2. US1 → pacote completo funcionando para o caminho feliz (MVP).
3. US2 → documento indisponível com motivo declarado não derruba mais o pacote.
4. US3 → integridade: divergência sem corroboração falha o job inteiro, sem entregar parcial.
5. Polish → suíte completa + validação ao vivo + revisão de infraestrutura (MEDIA_ROOT).

---

## Notes

- Nenhuma dependência nova de runtime (Princípio VIII); ZIP montado com `zipfile` da stdlib.
- `monta_pacote` e `run_pending_packages` nunca lançam exceção para o chamador (mesma garantia das
  features 009/010/011) — falha inesperada vira `status='failed'` com o erro registrado.
- FR-013 (documento que é ele mesmo um ZIP, incluído sem expandir) não exige código específico —
  é o comportamento natural de escrever os bytes baixados como uma entrada, sem inspecionar/abrir
  o conteúdo; não precisa de task própria além do caminho feliz de T018.
- Parar em qualquer checkpoint acima já entrega valor de forma independente e testável.
