# Tasks: Precedentes — dossiê de due diligence (fundação)

**Input**: Design documents from `/specs/013-precedentes-due-diligence/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/precedentes.md,
quickstart.md

**Tests**: incluídos — Princípio VII / Development Workflow item 2 da constituição. Sem nenhuma
chamada HTTP nesta spec, então nenhum teste precisa de fixture/mock de rede.

**Organization**: tarefas agrupadas por história de usuário. Histórias 1 e 2 (criar caso +
registrar fatos com evidência/status) formam juntas o MVP mínimo entregável, por decisão explícita
desta rodada de tasks — a linha do tempo de um caso sem nenhum fato não é útil sozinha.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Criar o app `apps/precedentes/` (`__init__.py`, `apps.py` com `PrecedentesConfig`,
  `migrations/__init__.py`, `tests/__init__.py`).
- [X] T002 Registrar `'apps.precedentes.apps.PrecedentesConfig'` em `INSTALLED_APPS` em
  `config/settings.py`.
- [X] T003 [P] Criar `apps/precedentes/urls.py` (vazio por ora, rotas vêm em US1/US2) e incluir em
  `config/urls.py` (`path('precedentes/', include('apps.precedentes.urls'))`).

**Checkpoint**: `python manage.py check` passa; app carrega sem erro.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: os 4 modelos — base de tudo que segue.

**⚠️ CRITICAL**: nenhuma história de usuário começa antes desta fase terminar.

- [X] T004 Criar os 4 modelos em `apps/precedentes/models.py` conforme data-model.md:
  `PrecedentCase`, `PrecedentEntity` (`papel` choices `requerente`/`parte_identificada`/`outro`),
  `PrecedentFact` (self-FK `root`, `is_current`, `status` choices
  `confirmado`/`confirmar_cliente`/`solicitar_cliente`/`nao_localizado`), `PrecedentAnalysis`
  (`facts` M2M).
- [X] T005 Gerar e revisar a migration: `./.venv/Scripts/python.exe manage.py makemigrations
  precedentes`.
- [X] T006 [P] Registrar os 4 modelos em `apps/precedentes/admin.py` (list_display simples,
  inlines de `PrecedentEntity`/`PrecedentFact` no admin do caso, se fizer sentido — cadastro manual
  via admin é um caminho de apoio, não a via principal).
- [X] T007 [P] Teste em `apps/precedentes/tests/test_models.py`: `PrecedentFact` criado sem `root`
  fica com `root=None`; um grupo de versões (raiz + 2 correções manuais via `objects.create`, sem
  passar pelo service ainda) é encontrável via `Q(id=raiz.id) | Q(root_id=raiz.id)`.

**Checkpoint**: `./.venv/Scripts/python.exe manage.py test apps.precedentes` passa (modelos e admin
carregando) antes de iniciar qualquer história de usuário.

---

## Phase 3: User Story 1+2 - Criar caso, adicionar/editar empresas, registrar fatos (Priority: P1) 🎯 MVP

**Goal**: um advogado autenticado cria um caso, adiciona/edita empresas com papel, e registra fatos
sobre cada empresa com evidência e status — a página do caso mostra tudo, com fatos pendentes
destacados.

**Independent Test**: criar um caso, adicionar 2 empresas, editar uma delas, registrar 3 fatos com
os 4 status diferentes, e confirmar que a página do caso mostra tudo corretamente agrupado/
destacado.

### Tests for User Story 1+2

- [X] T008 [P] [US1] Teste em `apps/precedentes/tests/test_services.py`: `create_case` cria o caso
  com `created_by` correto; `add_entity` cria a empresa associada ao caso.
- [X] T009 [P] [US1] Teste em `apps/precedentes/tests/test_services.py`: `update_entity` altera
  papel/razão social/CNPJ/país de uma empresa existente sem criar uma segunda linha (FR-002).
- [X] T010 [P] [US2] Teste em `apps/precedentes/tests/test_services.py`: `record_fact` com
  `status='confirmado'` e `fonte_descricao` preenchida cria o fato normalmente (FR-003).
- [X] T011 [P] [US2] Teste em `apps/precedentes/tests/test_services.py`: `record_fact` com
  `status='confirmado'` e SEM `fonte_descricao` nem `fonte_url` levanta `ValidationError` e não
  cria nada (FR-004).
- [X] T012 [P] [US2] Teste em `apps/precedentes/tests/test_services.py`: `record_fact` com `valor`
  vazio levanta `ValidationError` (FR-005).
- [X] T013 [P] [US2] Teste em `apps/precedentes/tests/test_services.py`: `record_fact` com
  `status='solicitar_cliente'` e sem fonte é aceito normalmente (a exigência de fonte é só para
  `confirmado`, FR-004 não se aplica aos outros status).
- [X] T014 [P] [US1] Teste de view em `apps/precedentes/tests/test_views.py`: `GET /precedentes/`
  sem autenticação redireciona para login; autenticado, lista os casos existentes.
- [X] T015 [P] [US1] Teste de view em `apps/precedentes/tests/test_views.py`: `POST
  /precedentes/novo/` cria o caso e redireciona para o detalhe; `POST
  /precedentes/empresas/<pk>/editar/` atualiza a empresa e redireciona de volta.
- [X] T016 [P] [US2] Teste de view em `apps/precedentes/tests/test_views.py`: `GET
  /precedentes/<pk>/` mostra as empresas e os fatos atuais de cada uma, agrupados por status, com
  os pendentes (`confirmar_cliente`/`solicitar_cliente`) visualmente destacados (verificar por
  classe CSS/contexto, não só pela presença do texto).

### Implementation for User Story 1+2

- [X] T017 [US1] Implementar `create_case`, `add_entity` e `update_entity` em
  `apps/precedentes/services.py`. *(depende de T008, T009)*
- [X] T018 [US2] Implementar `record_fact` em `apps/precedentes/services.py` com as validações de
  FR-004/FR-005. *(depende de T010, T011, T012, T013)*
- [X] T019 [US1] [US2] Implementar `apps/precedentes/selectors.py::current_facts(entity)`.
- [X] T020 [US1] Implementar as views `precedentes_list`/`case_create`/`entity_update` em
  `apps/precedentes/views.py` (`@login_required`) e as rotas correspondentes em
  `apps/precedentes/urls.py`. *(depende de T014, T015, T017)*
- [X] T021 [US2] Implementar a view de detalhe do caso e a de registro de fato (`POST
  /precedentes/empresas/<pk>/fatos/`) e o formulário inline no template. *(depende de T016, T018,
  T019)*
- [X] T022 [US1] [US2] Criar `templates/precedentes/list.html` (lista de casos, link "Novo caso")
  e `templates/precedentes/case_detail.html` (empresas com edição inline, fatos atuais agrupados
  por status com destaque visual para pendentes — FR-011; formulários de adicionar empresa/fato).

**Checkpoint**: US1+US2 completo e testável isoladamente — criar caso, adicionar/editar empresa,
registrar fato com/sem evidência, ver tudo na página do caso.

---

## Phase 4: User Story 3 - Corrigir fato sem perder histórico (Priority: P2)

**Goal**: corrigir um fato sempre cria uma nova versão, nunca apaga a anterior; o histórico
completo fica consultável.

**Independent Test**: registrar um fato, corrigi-lo duas vezes com motivos diferentes, e confirmar
que as 3 versões ficam visíveis no histórico, na ordem certa.

### Tests for User Story 3

- [X] T023 [P] [US3] Teste em `apps/precedentes/tests/test_services.py`: `correct_fact` com
  `motivo` preenchido cria uma nova versão (`root` aponta pra raiz, `is_current=True`), e a versão
  anterior passa a `is_current=False` sem ter o valor alterado (FR-006).
- [X] T024 [P] [US3] Teste em `apps/precedentes/tests/test_services.py`: `correct_fact` sem
  `motivo` levanta `ValidationError` e não altera nada (FR-007).
- [X] T025 [P] [US3] Teste em `apps/precedentes/tests/test_services.py`: corrigir a mesma raiz duas
  vezes seguidas produz 3 versões no total (raiz + 2 correções), todas encontráveis por
  `selectors.fact_history`, em ordem cronológica, cada uma com seu `motivo` (FR-008/FR-009).
- [X] T026 [P] [US3] Teste em `apps/precedentes/tests/test_services.py`: corrigir uma versão que
  NÃO é a raiz (corrigir a correção) resolve corretamente para o grupo (mesma raiz), não cria um
  grupo novo por engano.
- [X] T027 [P] [US3] Teste de view em `apps/precedentes/tests/test_views.py`: `GET
  /precedentes/fatos/<pk>/historico/` mostra as versões em ordem, com motivo de cada correção.

### Implementation for User Story 3

- [X] T028 [US3] Implementar `correct_fact` em `apps/precedentes/services.py` conforme
  contracts/precedentes.md. *(depende de T023, T024, T025, T026)*
- [X] T029 [US3] Implementar `apps/precedentes/selectors.py::fact_history(fact)`.
- [X] T030 [US3] Implementar a view/rota de correção e a página/seção de histórico
  (`templates/precedentes/case_detail.html` ou um template próprio para histórico). *(depende de
  T027, T028, T029)*

**Checkpoint**: US3 completo — correções nunca apagam histórico, tudo consultável.

---

## Phase 5: User Story 4 - Análise separada de fato (Priority: P2)

**Goal**: registrar uma análise associada a fatos-base, sempre distinta visualmente de um fato, e
a referência permanece íntegra mesmo quando um fato-base é corrigido.

**Independent Test**: registrar 2 fatos, uma análise citando os dois, corrigir um dos fatos, e
confirmar que a análise continua referenciando o fato (agora atualizado) sem quebrar.

### Tests for User Story 4

- [X] T031 [P] [US4] Teste em `apps/precedentes/tests/test_services.py`: `record_analysis` associa
  a análise aos fatos-base informados (via linha-raiz, mesmo se um fato não-raiz for passado por
  engano — resolve para a raiz).
- [X] T032 [P] [US4] Teste em `apps/precedentes/tests/test_services.py`: depois de `correct_fact`
  num fato-base de uma análise já existente, a análise continua associada (a raiz nunca muda) e o
  valor atual exibido para esse fato-base é o da versão corrigida, não a antiga (FR-010 cenário 2).
- [X] T033 [P] [US4] Teste de view em `apps/precedentes/tests/test_views.py`: a página do caso
  mostra fatos e análises em seções/destaque visualmente distintos, e as contagens de cada um
  aparecem separadas (FR-011, SC-003 verificável por presença de marcadores distintos no HTML).

### Implementation for User Story 4

- [X] T034 [US4] Implementar `record_analysis` em `apps/precedentes/services.py`. *(depende de
  T031, T032)*
- [X] T035 [US4] Implementar `apps/precedentes/selectors.py::case_analyses(case)`.
- [X] T036 [US4] Implementar a view/rota de registro de análise e a seção correspondente em
  `templates/precedentes/case_detail.html`, com destaque visual distinto de um fato (ex.: cor/
  rótulo "Análise" vs. "Fato"). *(depende de T033, T034, T035)*

**Checkpoint**: US4 completo — fato e análise nunca se confundem, mesmo depois de correções.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T037 Implementar `remove_entity` em `apps/precedentes/services.py` (FR-012: cascata nativa
  do Django remove os fatos da empresa; remove explicitamente qualquer `PrecedentAnalysis` do caso
  que fique com `facts.count() == 0` após a cascata) + a view/rota de remoção com confirmação
  prévia no template (spec.md, Edge Cases).
- [X] T038 [P] Teste em `apps/precedentes/tests/test_services.py`: `remove_entity` remove a
  empresa, seus fatos, e qualquer análise que dependia só dela; uma análise com fatos de OUTRA
  empresa sobrevive (SC-004 — nenhum registro órfão).
- [X] T039 Rodar `./.venv/Scripts/python.exe manage.py test apps.precedentes` e confirmar toda a
  suíte passando (quickstart.md, passo 1).
- [X] T040 Revisão dedicada confirmando FR-004/FR-007 (única "validação contra a realidade"
  possível nesta spec, já que não há rede): reler os testes T011 (confirmado sem fonte) e T024
  (correção sem motivo) e confirmar, por inspeção direta do código de `services.py`, que a
  validação roda ANTES de qualquer `objects.create`/`.save()` — nenhum estado parcial é gravado
  quando a validação falha (mesmo espírito da revisão de segurança da feature 011, adaptado ao
  risco desta spec: gravar dado inválido silenciosamente, não uma ação destrutiva).
- [X] T041 [P] Validar quickstart.md passo 2 (fluxo manual via shell) e confirmar que o resultado
  bate com o esperado.
- [X] T042 [P] Adicionar ao README uma linha sobre a nova seção "Precedentes" do painel (rótulo,
  onde encontrar), seguindo o padrão de features anteriores.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências.
- **Foundational (Phase 2)**: depende do Setup; bloqueia todas as histórias.
- **User Story 1+2 (Phase 3)**: depende só da Foundational — MVP.
- **User Story 3 (Phase 4)**: depende de US1+US2 (T018, `record_fact` cria a raiz que
  `correct_fact` corrige).
- **User Story 4 (Phase 5)**: depende de US1+US2 (T018, precisa de fatos existentes para
  referenciar) — não depende de US3 (uma análise pode referenciar um fato nunca corrigido).
- **Polish (Phase 6)**: depende de todas as histórias desejadas estarem completas (T037 usa
  `PrecedentAnalysis`, que só existe depois de US4).

### Parallel Opportunities

- T003 (Setup) pode rodar em paralelo com T001/T002.
- Dentro da Foundational: T006/T007 podem rodar em paralelo depois de T004/T005.
- Todos os testes `[P]` de uma mesma história podem ser escritos em paralelo entre si
  (T008-T016, T023-T027, T031-T033).
- US3 e US4 podem ser implementadas em paralelo por pessoas diferentes assim que US1+US2 terminar
  — não têm dependência lógica uma da outra (ambas só dependem de `record_fact` já existir).

---

## Implementation Strategy

### MVP First (User Story 1+2)

1. Completar Setup (T001-T003) e Foundational (T004-T007).
2. Completar User Story 1+2 (T008-T022).
3. Rodar `./.venv/Scripts/python.exe manage.py test apps.precedentes` e validar quickstart.md
   passos 1-2.
4. Esse já é o ganho mais caro: um caso com empresas e fatos com evidência/status já é due
   diligence utilizável, mesmo sem correção versionada ou análise separada ainda.

### Incremental Delivery

1. Setup + Foundational → modelos prontos.
2. US1+US2 → caso + empresas + fatos com evidência (MVP).
3. US3 → correção nunca apaga histórico.
4. US4 → análise estruturalmente separada de fato.
5. Polish → remoção de empresa (com limpeza de análise órfã) + suíte completa + revisão FR-004/007.

---

## Notes

- Nenhuma dependência nova (Princípio VIII); nenhuma chamada de rede nesta spec — todos os testes
  são diretos, sem mock de HTTP.
- `services.py` é onde toda regra de negócio mora — views apenas validam formulário e chamam o
  service (mesmo padrão de todas as features anteriores).
- Esta é só a fundação da iniciativa "Precedentes" — pesquisa societária, jurisprudência, extração
  de documentos e relatório final são specs futuras, cada uma com seu próprio spec-kit completo.
- Parar em qualquer checkpoint acima já entrega valor de forma independente e testável.
