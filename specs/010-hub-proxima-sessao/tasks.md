# Tasks: Próxima sessão de julgamento no dashboard

**Input**: Design documents from `/specs/010-hub-proxima-sessao/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/hub.md, quickstart.md

**Tests**: incluídos — Princípio VII / Development Workflow item 2 e 3 da constituição.

**Organization**: tarefas agrupadas por história de usuário (US1/US2 do spec.md).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Adicionar `CACHES = {'default': {'BACKEND':
  'django.core.cache.backends.db.DatabaseCache', 'LOCATION': 'cache_hub'}}` em
  `config/settings.py` (sem env nova — é infraestrutura interna, não credencial).
- [X] T002 [P] Adicionar em `config/env_schema.py`/`config/settings.py` a variável
  `HUB_FETCH_MIN_INTERVAL_SECONDS` (default `3600` — calendário/pauta mudam poucas vezes por mês,
  não precisa da cadência de 5 min do DOU) e documentar no `.env.example`.
- [X] T003 Criar `apps/dashboard/tests/__init__.py` e `apps/dashboard/tests/fixtures/__init__.py`
  (helper `load_fixture`, mesmo padrão de `apps/dou/tests/fixtures/__init__.py`) — o app
  `dashboard` ainda não tem pasta `tests/` estruturada para fixtures.

**Checkpoint**: `python manage.py createcachetable` roda sem erro; `python manage.py check` passa.

---

## Phase 2: User Story 1 - Ver a próxima sessão de julgamento ao abrir o dashboard (Priority: P1) 🎯 MVP

**Goal**: o dashboard mostra a sessão futura mais próxima (cache), nunca faz HTTP na view.

**Independent Test**: fixture do calendário com sessão futura e passada; refresh popula o cache;
`proxima_sessao()` devolve só a futura.

### Tests for User Story 1

- [X] T004 [P] [US1] Fixture em `apps/dashboard/tests/fixtures/calendario_sessoes.html` (HTML
  simplificado no padrão ano→mês→dia, com pelo menos 2 sessões: uma cuja data cai no
  passado relativo a uma data de teste fixa, outra no futuro).
  `apps/dashboard/tests/fixtures/calendario_sem_sessao_futura.html` (só sessões passadas).
- [X] T005 [P] [US1] Teste em `apps/dashboard/tests/test_hub.py`: `sessoes_do_html` extrai
  `[(data_iso, titulo), ...]` corretamente do fixture T004.
- [X] T006 [P] [US1] Teste em `apps/dashboard/tests/test_hub.py` (mock de `urlopen` + `cache`):
  `refresh_sessoes` busca a fonte, grava `cache.get('hub:sessoes')` com o resultado de
  `sessoes_do_html`, e uma segunda chamada dentro do intervalo mínimo (`HUB_FETCH_MIN_INTERVAL_SECONDS`)
  não faz HTTP de novo.
- [X] T007 [P] [US1] Teste em `apps/dashboard/tests/test_hub.py`: com o cache pré-populado (sem
  mock de HTTP), `proxima_sessao()` devolve a sessão futura mais próxima, nunca uma passada, e
  nunca chama `urlopen`.
- [X] T008 [P] [US1] Teste em `apps/dashboard/tests/test_hub.py`: cache vazio (nunca populado) →
  `proxima_sessao()` devolve `None` sem lançar exceção.
- [X] T009 [P] [US1] Teste em `apps/dashboard/tests/test_hub.py`: `refresh_sessoes` com `urlopen`
  levantando erro de rede → não lança exceção, cache permanece com o valor anterior (ou vazio).
- [X] T010 [P] [US1] Teste em `apps/dashboard/tests/test_views.py` (ou arquivo de teste de views já
  existente do app `dashboard`, se houver): `GET /` com `proxima_sessao()` mockado retornando uma
  sessão → o HTML da resposta contém a data/título; mockado retornando `None` → a página carrega
  normalmente (200), sem o cartão e sem erro.

### Implementation for User Story 1

- [X] T011 [US1] Implementar `sessoes_do_html(html: str) -> list[tuple[str, str]]` em
  `apps/dashboard/hub.py` (mesma lógica linha-a-linha ano→mês→dia). *(depende de T005)*
- [X] T012 [US1] Implementar `refresh_sessoes(timeout, user_agent)` em `apps/dashboard/hub.py`:
  gate de cadência via `cache.get/set('hub:last_attempt:sessoes', ...)`, HTTP GET (stdlib
  `urllib`, mesmo padrão de `apps/monitoring/clients.py`), parsing via T011, grava
  `cache.set('hub:sessoes', sessoes, timeout=7*24*3600)`; nunca lança exceção para o chamador.
  *(depende de T006, T009, T011)*
- [X] T013 [US1] Implementar `proxima_sessao() -> dict | None` em `apps/dashboard/hub.py`: lê
  `cache.get('hub:sessoes')`, filtra por `data >= hoje`, devolve a mais próxima ou `None`. Nunca
  faz HTTP. *(depende de T007, T008)*
- [X] T014 [US1] Atualizar `apps/dashboard/views.py::index` para incluir `proxima_sessao()` no
  contexto do template (`'sessao': proxima_sessao()`). *(depende de T013)*
- [X] T015 [US1] Atualizar `templates/dashboard/index.html` com o cartão condicional (`{% if
  sessao %}`) mostrando data (formatada) e título. *(depende de T014)*
- [X] T016 [US1] Integrar `refresh_sessoes` em `apps/monitoring/management/commands/
  run_worker.py::_run_cycle`, mesmo padrão try/except + log dos passos já existentes (ver
  contracts/hub.md). *(depende de T012)*

**Checkpoint**: US1 completo e testável isoladamente — cartão de sessão funcionando de ponta a
ponta, sem link de pauta ainda.

---

## Phase 3: User Story 2 - Ver o link da pauta, quando publicada (Priority: P2)

**Goal**: o cartão da História 1 ganha um link para o PDF da pauta, quando já disponível.

**Independent Test**: fixture da página anual de pautas com/sem o PDF da sessão em exibição;
`pauta_url()` devolve o link ou `''` conforme o caso, sem nunca fazer HTTP.

### Tests for User Story 2

- [X] T017 [P] [US2] Fixtures em `apps/dashboard/tests/fixtures/`: `pautas_2026_com_pdf.html`
  (contém um link `cdn.cade.gov.br/.../2026/269/....pauta....pdf`), `pautas_2026_sem_pdf.html`
  (sem nenhum link de pauta para a sessão em teste).
- [X] T018 [P] [US2] Teste em `apps/dashboard/tests/test_hub.py`: `pauta_do_html(html, ano,
  numero)` extrai a URL correta do fixture "com PDF"; devolve `''` no fixture
  "sem PDF".
- [X] T019 [P] [US2] Testes em `apps/dashboard/tests/test_hub.py` (mock de `urlopen` + `cache`):
  `refresh_pauta` busca a fonte, grava `cache.get(f'hub:pauta:{ano}:{numero}')`, respeita a
  cadência mínima (mesmo padrão de T006), usa TTL menor (6h) quando não encontrou nada vs. TTL
  maior (7 dias) quando encontrou, **e** (FR-007) com `urlopen` levantando erro de rede não lança
  exceção — mesma garantia de T009, agora para a pauta.
- [X] T020 [P] [US2] Teste em `apps/dashboard/tests/test_hub.py`: com o cache de pauta
  pré-populado, `pauta_url(sessao)` devolve a URL sem fazer HTTP; cache vazio → devolve `''`.
- [X] T021 [P] [US2] Teste em `tests/test_views.py` (mesmo arquivo/classe de T010): `GET /` com `pauta_url()`
  mockada retornando uma URL nas duas variações (com e sem sessão futura) — o link aparece só
  quando há sessão E pauta; nenhum link quebrado quando só há sessão.

### Implementation for User Story 2

- [X] T022 [US2] Implementar `pauta_do_html(html, ano, numero)` em `apps/dashboard/hub.py`.
  *(depende de T018)*
- [X] T023 [US2] Implementar `refresh_pauta(timeout, user_agent)` em `apps/dashboard/hub.py`:
  chama `proxima_sessao()` primeiro (sem sessão futura conhecida, retorna sem HTTP); extrai
  ano/número do título (regex `\d+ª`); gate de cadência; HTTP GET; parsing via T022; grava no
  cache com o TTL correto conforme achou ou não. *(depende de T013, T019, T022)*
- [X] T024 [US2] Implementar `pauta_url(sessao) -> str` em `apps/dashboard/hub.py`: extrai
  ano/número de `sessao`, lê o cache, devolve `''` se ausente. Nunca faz HTTP. *(depende de T020)*
- [X] T025 [US2] Atualizar `apps/dashboard/views.py::index` para incluir `pauta_url(sessao) if
  sessao else ''` no contexto. *(depende de T024)*
- [X] T026 [US2] Atualizar `templates/dashboard/index.html` com o link condicional dentro do
  cartão de sessão. *(depende de T025)*
- [X] T027 [US2] Integrar `refresh_pauta` em `_run_cycle`, logo após `refresh_sessoes` (T016).
  *(depende de T023)*

**Checkpoint**: US2 completo — cartão com link de pauta quando disponível.

---

## Phase 4: Polish & Cross-Cutting Concerns

- [X] T028 Rodar `python manage.py test apps.dashboard` e confirmar toda a suíte passando
  (quickstart.md, passo 1).
- [X] T029 Validar manualmente contra as fontes reais seguindo `quickstart.md` passos 2-3 (1-2
  chamadas reais cada — nunca em loop). Documentar qualquer divergência em research.md,
  "Correção pós-implementação", seguindo o modelo das features 008/009.
- [X] T030 [P] Confirmar `python manage.py createcachetable` documentado no README (seção de
  setup/deploy) como passo obrigatório de instalação.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências.
- **User Story 1 (Phase 2)**: depende do Setup (T001-T003) — pode ser entregue sozinha como MVP.
- **User Story 2 (Phase 3)**: depende de US1 (usa `proxima_sessao()` de T013 para saber qual
  pauta buscar) — diferente da feature 009, aqui as histórias NÃO são independentes uma da outra
  (a pauta é sempre da sessão já identificada pela História 1).
- **Polish (Phase 4)**: depende de todas as histórias desejadas estarem completas.

### Parallel Opportunities

- T002/T003 (Setup) podem rodar em paralelo com T001.
- Todos os testes marcados `[P]` de uma mesma história (T004-T010, T017-T021) podem ser escritos
  em paralelo entre si.

---

## Implementation Strategy

### MVP First (User Story 1)

1. Completar Setup (T001-T003).
2. Completar User Story 1 (T004-T016).
3. Rodar `python manage.py test apps.dashboard` e validar `quickstart.md` passos 1-2.

### Incremental Delivery

1. Setup → cache configurado.
2. US1 → cartão de sessão funcionando (MVP).
3. US2 → link de pauta quando disponível.
4. Polish → suíte completa + validação ao vivo + doc de setup.

---

## Notes

- Sem app novo (diferente da feature 009) — tudo em `apps/dashboard/hub.py`, ver plan.md
  "Structure Decision".
- Nenhuma emenda de constituição necessária — ver plan.md, Constitution Check.
- `refresh_sessoes`/`refresh_pauta` nunca lançam exceção para `run_worker` (mesma garantia das
  features 008/009).
