# Tasks: Digest diário do DOU

**Input**: Design documents from `/specs/009-digest-diario-dou/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/dou-services.md,
quickstart.md

**Tests**: incluídos — a constituição do projeto exige testes com fixtures locais para
scrapers/extractors e cobertura de services (Princípio VII / Development Workflow item 2 e 3).

**Organization**: tarefas agrupadas por história de usuário (US1/US2/US3 do spec.md), na mesma
ordem de prioridade. Cada história inclui sua própria integração em `run_worker._run_cycle`, para
ser entregável e testável de ponta a ponta sozinha.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história de usuário à qual a tarefa pertence
- Caminhos de arquivo exatos em cada descrição

---

## Phase 1: Setup

**Purpose**: criar o esqueleto do app novo e as variáveis de configuração compartilhadas por
todas as histórias, sem nenhum comportamento ainda.

- [X] T001 Criar o app `apps/dou/` (`__init__.py`, `apps.py` com `DouConfig`, `migrations/__init__.py`,
  `tests/__init__.py`, `tests/fixtures/__init__.py`) seguindo o padrão dos apps existentes (ex.
  `apps/subscribers/apps.py`).
- [X] T002 Registrar `'apps.dou.apps.DouConfig'` em `INSTALLED_APPS` em `config/settings.py`, logo
  após `'apps.subscribers.apps.SubscribersConfig'`.
- [X] T003 [P] Adicionar em `config/env_schema.py` os campos novos (com default e leitura de env,
  seguindo o padrão de `worker_tick_seconds`/`app_timezone` já existentes):
  `dou_digest_window_start` (`'08:30'`), `dou_digest_window_end` (`'11:30'`),
  `dou_fetch_min_interval_seconds` (`300`, cobre a cadência de 5 min da emenda v2.2.0),
  `dou_anticipation_cutoff` (`'22:00'`), `dou_confirmation_window_start` (`'07:00'`),
  `dou_confirmation_window_end` (`'11:00'`).
- [X] T004 [P] Expor as variáveis de T003 em `config/settings.py` (bloco perto de
  `WORKER_TICK_SECONDS`), como `DOU_DIGEST_WINDOW_START`, `DOU_DIGEST_WINDOW_END`,
  `DOU_FETCH_MIN_INTERVAL_SECONDS`, `DOU_ANTICIPATION_CUTOFF`, `DOU_CONFIRMATION_WINDOW_START`,
  `DOU_CONFIRMATION_WINDOW_END`. Documentar cada uma no `.env.example` (Development Workflow item
  4 da constituição).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: modelos de dados, admin e as funções de baixo nível (HTTP, normalização de formato)
compartilhadas por todas as histórias de usuário.

**⚠️ CRITICAL**: nenhuma história de usuário começa antes desta fase terminar.

- [X] T005 Criar os 5 modelos em `apps/dou/models.py` conforme `data-model.md`: `DouSubscription`,
  `DouMonitoredTerm`, `DouSendLog` (com `Kind` choices `digest`/`pubdou_ant`/`pubdou_compl`/
  `pubdou_conf` e `unique_together=('subscription','kind','reference_date')`), `DouFetchState`
  (`source` choices `resenha`/`ingov_listing`, `unique=True`), `DouAnticipation`
  (`unique_together=('subscription','reference_date')`).
- [X] T006 Gerar e revisar a migration: `python manage.py makemigrations dou`.
- [X] T007 [P] Registrar os 5 modelos em `apps/dou/admin.py` (list_display simples, sem
  customização de UI dedicada — cadastro manual via Django admin nesta versão).
- [X] T008 [P] Criar `apps/dou/selectors.py` com `active_digest_subscriptions()`,
  `active_anticipation_subscriptions()`, `already_sent(subscription, kind, reference_date) -> bool`
  (consulta `DouSendLog`) e `monitored_terms(subscription) -> list[str]`.
- [X] T009 [P] Criar `apps/dou/clients.py` com o helper HTTP base (`_open_request`, reaproveitando
  literalmente o padrão de retry/backoff de `apps/monitoring/clients.py:_open_request` — mesma
  leitura de `settings.REQUEST_RETRY_ATTEMPTS`/`REQUEST_RETRY_BACKOFF_SECONDS`, mesmos headers
  `User-Agent`/`Accept`/`Accept-Language`) e a exceção `FetchError` (reaproveitar
  `apps.monitoring.clients.FetchError` por import, não duplicar a classe).
- [X] T010 [P] Criar `apps/dou/services.py::_should_fetch(source: str, now: datetime) -> bool`:
  lê/atualiza `DouFetchState` para a fonte informada, aplicando o intervalo mínimo
  `settings.DOU_FETCH_MIN_INTERVAL_SECONDS` (T003/T004) — usada por todas as histórias antes de
  qualquer chamada HTTP.
- [X] T011 [P] Teste em `apps/dou/tests/test_selectors.py`: `already_sent` retorna `True` só depois
  de um `DouSendLog` existir para a combinação exata (subscription, kind, reference_date); `False`
  para uma combinação diferente de qualquer um dos três campos.
- [X] T012 [P] Teste em `apps/dou/tests/test_services.py`: `_should_fetch` retorna `False` quando
  chamado duas vezes seguidas para a mesma fonte dentro do intervalo mínimo (mock do relógio) e
  `True` depois do intervalo passar; fontes diferentes (`resenha` vs `ingov_listing`) não competem
  pelo mesmo marcador.

**Checkpoint**: `python manage.py test apps.dou` passa (modelos, admin carregando, selectors e
cadência testados) antes de iniciar qualquer história de usuário.

---

## Phase 3: User Story 1 - Digest diário das publicações do CADE no DOU (Priority: P1) 🎯 MVP

**Goal**: todo assinante ativo do digest recebe, uma vez por dia dentro da janela configurada, um
e-mail com as publicações do CADE do dia (ou aviso de que não houve nenhuma), com negrito e
destaque por termo monitorado.

**Independent Test**: com fixtures da Resenha (dia com publicações, dia sem nenhuma) e da listagem
in.gov.br (fallback), rodar `run_digest_window` e conferir o conteúdo/quantidade de e-mails
enviados e os registros em `DouSendLog`.

### Tests for User Story 1

- [X] T013 [P] [US1] Criar fixtures em `apps/dou/tests/fixtures/`: `resenha_com_publicacoes.json`
  (1 edital + 2 despachos citando "Ato de Concentração nº 08700.001234/2026-11", um despacho longo
  o bastante para truncar, e uma pauta/ata do dia com link), `resenha_vazia.json` (sem publicações
  do CADE), `ingov_listing_com_publicacoes.json` (mesmo conteúdo do primeiro fixture, no formato
  bruto da listagem in.gov.br, incluindo itens de outros órgãos para exercitar o filtro por CADE e
  o mesmo artigo agrupado repetido em duas linhas do índice, para exercitar a deduplicação
  intra-fonte de FR-016).
- [X] T014 [P] [US1] Teste em `apps/dou/tests/test_parsers.py`: `parse_resenha_html` (ou o parser
  que ler o fixture JSON/HTML da Resenha) extrai editais/despachos no formato normalizado
  `{'editais': [...], 'despachos': [...], 'atas': [...]}`.
- [X] T015 [P] [US1] Teste em `apps/dou/tests/test_parsers.py`: `parse_ingov_listing` filtra
  itens para incluir só os que citam o CADE (campo de hierarquia/órgão), descartando os demais,
  produz o mesmo formato normalizado de T014, **e** deduplica o artigo repetido do fixture T013
  (FR-016) — o mesmo item nunca aparece duas vezes na lista de saída.
- [X] T016 [P] [US1] Teste em `apps/dou/tests/test_render.py`: `render_digest_text`/
  `render_digest_html` colocam o título do caso e os nomes de partes em negrito/destaque
  estrutural, e o despacho longo do fixture sai truncado (início + "(...)" + conclusão).
- [X] T017 [P] [US1] Teste em `apps/dou/tests/test_render.py`: um termo monitorado presente no
  texto de um item faz esse bloco sair com marcação de destaque (ex. `background-color` no HTML);
  o mesmo item, para um assinante sem esse termo, sai sem destaque.
- [X] T018 [P] [US1] Teste em `apps/dou/tests/test_render.py` (FR-007): a pauta/ata do fixture
  T013 aparece no rodapé do e-mail com título e link para o DOU; um segundo cenário, com o mesmo
  item mas sem URL disponível, aparece só com o título (sem link quebrado), conforme o Edge Case
  da spec.
- [X] T019 [P] [US1] Teste em `apps/dou/tests/test_render.py`: dia sem nenhuma publicação produz
  uma mensagem explícita de "sem publicações" (não uma seção vazia silenciosa).
- [X] T020 [P] [US1] Teste em `apps/dou/tests/test_clients.py` (mock de `urlopen`):
  `fetch_resenha` retorna `None` quando a resposta indica que a Resenha do dia ainda não está
  disponível (sem lançar exceção); levanta `FetchError` em erro de rede/timeout.
- [X] T021 [P] [US1] Teste em `apps/dou/tests/test_services.py`: `run_digest_window` fora da
  janela diária configurada (`DOU_DIGEST_WINDOW_START`/`_END`) não faz nenhuma chamada HTTP
  (mock) e retorna `{'skipped': True, ...}`.
- [X] T022 [P] [US1] Teste em `apps/dou/tests/test_services.py`: dentro da janela, com a Resenha
  disponível (fixture T013), `run_digest_window` envia exatamente 1 e-mail por assinante ativo
  (mock de `send_email_notification`) e grava 1 `DouSendLog(kind='digest')` por assinante.
- [X] T023 [P] [US1] Teste em `apps/dou/tests/test_services.py`: chamar `run_digest_window` duas
  vezes no mesmo dia (já com `DouSendLog` gravado da primeira vez) não envia um segundo e-mail
  (idempotência, FR-005/FR-012).
- [X] T024 [P] [US1] Teste em `apps/dou/tests/test_services.py`: quando `fetch_resenha` retorna
  `None`, `run_digest_window` tenta `fetch_ingov_listing` (mock) e usa o resultado dela para
  montar e enviar o digest.
- [X] T025 [P] [US1] Teste em `apps/dou/tests/test_services.py`: assinante com
  `subscriber.silent_mode=True` (ou `paused_until` no futuro) não recebe e-mail, mesmo estando
  `DouSubscription.enabled=True` (FR-014, reaproveitando `Subscriber.is_reachable()`).

### Implementation for User Story 1

- [X] T026 [US1] Implementar `fetch_resenha(date, timeout, user_agent)` e
  `fetch_ingov_listing(date, timeout, user_agent)` em `apps/dou/clients.py`, usando o helper HTTP
  de T009. *(depende de T009)*
- [X] T027 [US1] Implementar `parse_resenha_html` / `parse_ingov_listing` (+ filtro por CADE +
  deduplicação intra-fonte de itens repetidos, FR-016) em `apps/dou/parsers.py`, produzindo o
  formato normalizado `{'editais', 'despachos', 'atas'}` consumido por `render.py`
  independentemente da fonte. *(depende de T014, T015)*
- [X] T028 [US1] Implementar `render_digest_text` / `render_digest_html` em `apps/dou/render.py`:
  negrito de título/partes, truncamento de despacho longo (início + conclusão), destaque por
  termo monitorado (fold sem acento/caixa, fronteira de palavra), rodapé com pautas/atas do dia
  (título + link quando disponível, só título quando não, sem PDF), e mensagem específica para dia
  sem publicação. *(depende de T016, T017, T018, T019)*
- [X] T029 [US1] Implementar `run_digest_window(now)` em `apps/dou/services.py`: `_should_fetch`
  (T010) → `fetch_resenha` → fallback `fetch_ingov_listing` (T026) → `parsers` (T027) →
  `render` (T028) → para cada assinatura de `active_digest_subscriptions()` (T008) não marcada em
  `already_sent` (T008) e com `subscriber.is_reachable()`, chama
  `send_email_notification` (`apps/notifications/channels/email.py`) e grava `DouSendLog` com
  `status='sent'` em sucesso ou `status='failed'`+`error` em falha (nunca omite o registro,
  SC-003); nunca lança exceção para o chamador (captura e loga, conta em `failed`). *(depende de
  T026, T027, T028)*
- [X] T030 [US1] Integrar `run_digest_window` em `apps/monitoring/management/commands/
  run_worker.py::_run_cycle`, entre o passo 2 (processos vencidos) e o passo 3 (notificações
  pendentes), no mesmo padrão try/except + `sentry_sdk.capture_exception` + log dos passos já
  existentes (ver contracts/dou-services.md). *(depende de T029)*

**Checkpoint**: US1 completo e testável isoladamente — `python manage.py test apps.dou` cobre o
digest diário de ponta a ponta, e o worker já dispara o digest em produção/dev.

---

## Phase 4: User Story 2 - Antecipação da véspera (Priority: P2)

**Goal**: assinante com antecipação habilitada recebe, no horário configurado, um e-mail
antecipando os andamentos do boletim do SEI que devem sair no DOU do dia seguinte, com
complemento se surgirem itens novos até um horário-limite da noite.

**Independent Test**: com fixtures do boletim/resenha do SEI (2 andamentos relevantes, depois 1
item novo numa checagem posterior, depois um dia sem nada), rodar `run_anticipation_window`
repetidamente e conferir os e-mails e o `DouAnticipation` persistido.

### Tests for User Story 2

- [X] T031 [P] [US2] Fixture em `apps/dou/tests/fixtures/sei_boletim_dois_andamentos.json`
  (2 andamentos relevantes) e `sei_boletim_um_andamento_novo.json` (os mesmos 2 + 1 novo).
- [X] T032 [P] [US2] Teste em `apps/dou/tests/test_services.py`: assinante com
  `nextday_enabled=True` e `now` já passado do `nextday_time` configurado recebe, na primeira
  chamada de `run_anticipation_window`, um e-mail com os 2 andamentos do fixture T031, e um
  `DouAnticipation(reference_date=amanhã)` é gravado com esses itens.
- [X] T033 [P] [US2] Teste em `apps/dou/tests/test_services.py`: uma segunda chamada de
  `run_anticipation_window`, ainda no mesmo dia e antes de `DOU_ANTICIPATION_CUTOFF`, usando o
  fixture com o item novo (T031), envia um e-mail complementar contendo **só** o item novo (sem
  repetir os 2 já antecipados), e atualiza o `DouAnticipation` existente.
- [X] T034 [P] [US2] Teste em `apps/dou/tests/test_services.py`: nenhum andamento relevante no
  boletim do SEI → o assinante recebe um e-mail curto de "sem publicações previstas" no horário
  configurado (não a ausência de e-mail).
- [X] T035 [P] [US2] Teste em `apps/dou/tests/test_services.py`: assinante com
  `nextday_enabled=False` nunca recebe e-mail de antecipação, mesmo com andamentos relevantes no
  boletim do SEI.
- [X] T036 [P] [US2] Teste em `apps/dou/tests/test_services.py` (FR-012/SC-002): chamar
  `run_anticipation_window` duas vezes seguidas sem que o boletim do SEI tenha mudado (sem item
  novo) não reenvia nenhum e-mail nem atualiza `DouAnticipation` além do já gravado — mesma
  garantia de idempotência de T023, agora para a antecipação.
- [X] T037 [P] [US2] Teste em `apps/dou/tests/test_services.py` (FR-014): assinante com
  `subscriber.silent_mode=True` e `nextday_enabled=True` não recebe e-mail de antecipação, mesmo
  com andamentos relevantes no boletim do SEI — mesma garantia de T025, agora para a antecipação.
- [X] T038 [P] [US2] Teste em `apps/dou/tests/test_services.py`: chamada de
  `run_anticipation_window` depois de `DOU_ANTICIPATION_CUTOFF` não gera mais nenhum e-mail
  complementar, mesmo com itens novos no boletim.

### Implementation for User Story 2

- [X] T039 [US2] Implementar `run_anticipation_window(now)` em `apps/dou/services.py`,
  reaproveitando a extração de andamentos já existente em `apps/monitoring/extractors.py` sobre o
  boletim do SEI (mesma fonte que o monitoramento de processo já lê); usa `render_pubdou_text`/
  `_html` (T040) e persiste/atualiza `DouAnticipation`; grava `DouSendLog` (sucesso ou falha,
  mesma garantia de T029) para cada envio; nunca lança exceção para o chamador. *(depende de T008)*
- [X] T040 [US2] Implementar `render_pubdou_text` / `render_pubdou_html` (antecipação e
  complemento) em `apps/dou/render.py`, reaproveitando o mesmo motor de negrito/destaque de T028.
- [X] T041 [US2] Integrar `run_anticipation_window` em `_run_cycle` (mesmo bloco de T030, logo
  após `run_digest_window`). *(depende de T039)*

**Checkpoint**: US2 completo — antecipação e complemento funcionam de ponta a ponta, sem afetar o
digest de US1.

---

## Phase 5: User Story 3 - Confirmação da manhã (Priority: P3)

**Goal**: na manhã seguinte, assinante com antecipação recebe a confirmação do que foi
efetivamente publicado, com "exceto ..." para o que ficou de fora, respeitando concordância
singular/plural.

**Independent Test**: com um `DouAnticipation` fixo e fixtures do DOU real do dia seguinte em três
variações (tudo publicado, algo faltando, nada publicado), rodar `run_confirmation_window` e
conferir o texto/lista gerada.

### Tests for User Story 3

- [X] T042 [P] [US3] Teste em `apps/dou/tests/test_services.py`: `DouAnticipation` com 3 itens e
  DOU real (fixture) confirmando os 3 → e-mail de confirmação lista os 3 com o texto do DOU real,
  linguagem "todos os andamentos abaixo".
- [X] T043 [P] [US3] Teste em `apps/dou/tests/test_services.py`: `DouAnticipation` com 2 itens e
  DOU real confirmando só 1 → e-mail menciona explicitamente o item faltante ("... exceto
  [referência]").
- [X] T044 [P] [US3] Teste em `apps/dou/tests/test_services.py`: `DouAnticipation` com exatamente
  1 item não publicado → texto usa concordância singular ("o andamento abaixo ...").
- [X] T045 [P] [US3] Teste em `apps/dou/tests/test_services.py`: DOU real do dia sem nenhuma
  publicação do CADE → e-mail de aviso curto, sem a linguagem de "todos os itens abaixo".
- [X] T046 [P] [US3] Teste em `apps/dou/tests/test_services.py`: assinante sem `DouAnticipation`
  para a data de hoje (não habilitou US2, ou não havia nada a antecipar) não recebe e-mail de
  confirmação.
- [X] T047 [P] [US3] Teste em `apps/dou/tests/test_services.py` (FR-012/SC-002): chamar
  `run_confirmation_window` duas vezes no mesmo dia não envia um segundo e-mail de confirmação
  para o mesmo assinante — mesma garantia de T023/T036, agora para a confirmação.
- [X] T048 [P] [US3] Teste em `apps/dou/tests/test_services.py` (FR-014): assinante com
  `subscriber.paused_until` no futuro não recebe e-mail de confirmação, mesmo tendo uma
  `DouAnticipation` pendente de confirmar — mesma garantia de T025/T037, agora para a confirmação.

### Implementation for User Story 3

- [X] T049 [US3] Implementar `run_confirmation_window(now)` em `apps/dou/services.py`: para cada
  `DouAnticipation` de hoje, busca o DOU real do dia (reaproveita `fetch_resenha`/
  `fetch_ingov_listing` de T026, com o próprio `DouFetchState` — não compete pela cadência de
  `run_digest_window`), compara itens antecipados × publicados por referência de processo, monta
  a lista de faltantes, chama `render_confirmation_text`/`_html` (T050) e envia; grava
  `DouSendLog(kind='pubdou_conf')` (sucesso ou falha, mesma garantia de T029/T039). *(depende de
  T026, T039)*
- [X] T050 [US3] Implementar `render_confirmation_text` / `render_confirmation_html` em
  `apps/dou/render.py`, com a concordância singular/plural e a mensagem específica de "nada
  publicado" (FR-010/FR-011).
- [X] T051 [US3] Integrar `run_confirmation_window` em `_run_cycle` (mesmo bloco de T030/T041,
  logo após `run_anticipation_window`). *(depende de T049)*

**Checkpoint**: US3 completo — o ciclo antecipação → confirmação funciona de ponta a ponta.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T052 Rodar `python manage.py test apps.dou apps.monitoring` e confirmar toda a suíte
  (existente + nova) passando (quickstart.md, passo 1).
- [X] T053 Validar manualmente contra as fontes reais seguindo `quickstart.md` passo 3 (1-2
  chamadas reais à Resenha e à listagem in.gov.br — nunca em loop). Documentar qualquer
  divergência entre o formato real e o assumido em `parsers.py` numa seção "Correção
  pós-implementação" em `research.md`, seguindo o modelo de
  `specs/008-endurecer-scraper-sei/research.md` item 6; ajustar `parsers.py` se necessário.
- [X] T054 [P] Validar `quickstart.md` passo 4 (cadência de 5 min + janela diária) com o comando
  de teste indicado.
- [X] T055 [P] Revisar `.env.example` e a seção do README sobre o worker (se existir) para
  mencionar as novas variáveis `DOU_*` de T003/T004.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências — pode começar imediatamente.
- **Foundational (Phase 2)**: depende do Setup (T001-T004); bloqueia todas as histórias de
  usuário.
- **User Story 1 (Phase 3)**: depende só da Foundational — pode ser entregue sozinha como MVP.
- **User Story 2 (Phase 4)**: depende só da Foundational (T008-T010), não de US1 (motor de
  formatação é compartilhado por composição, não por dependência de código entre fases).
- **User Story 3 (Phase 5)**: depende da Foundational **e** de US1 (T026, busca do DOU real) e de
  US2 (T039, é o que produz o `DouAnticipation` que a confirmação lê).
- **Polish (Phase 6)**: depende de todas as histórias desejadas estarem completas.

### Parallel Opportunities

- T003/T004 (Setup) podem rodar em paralelo com T001/T002.
- Dentro da Foundational: T007-T012 podem rodar em paralelo entre si depois de T005/T006.
- Todos os testes de uma mesma história marcados `[P]` (T013-T025, T031-T038, T042-T048) podem
  ser escritos em paralelo entre si.
- US1 e US2 podem ser implementadas em paralelo por pessoas diferentes assim que a Foundational
  terminar — não compartilham arquivo de implementação além de `services.py`/`render.py` (exigem
  coordenação de merge, mas sem dependência lógica).
- US3 só pode começar depois de US1 (T026) e US2 (T039) estarem prontas.

---

## Implementation Strategy

### MVP First (User Story 1)

1. Completar Setup (T001-T004) e Foundational (T005-T012).
2. Completar User Story 1 (T013-T030).
3. Rodar `python manage.py test apps.dou` e validar `quickstart.md` passos 1-2.
4. Esse já é o ganho mais caro (spec.md: User Story 1 é P1 — sem ela não há digest algum).

### Incremental Delivery

1. Setup + Foundational → modelos, admin, cadência de busca prontos.
2. US1 → digest diário funcionando de ponta a ponta (MVP).
3. US2 → antecipação da véspera, opcional por assinante.
4. US3 → confirmação da manhã, fecha o ciclo de US2.
5. Polish → suíte completa + validação ao vivo + documentação.

---

## Notes

- Nenhuma dependência nova de runtime é introduzida (Princípio VIII); PDF de ata/pauta e leitura
  de PDF de seção ficam fora de escopo (spec.md, Assumptions).
- Toda requisição HTTP passa pelo helper de `apps/dou/clients.py` (retry/backoff herdado do padrão
  de `apps/monitoring/clients.py`) — nunca chamar `urllib.request.urlopen` diretamente.
- `run_digest_window`, `run_anticipation_window` e `run_confirmation_window` nunca lançam exceção
  para `run_worker` — cada uma captura e loga suas próprias falhas (ver contracts/dou-services.md).
- Deduplicação (FR-016) é sempre intra-fonte (a mesma fonte listando o mesmo item duas vezes),
  nunca entre Resenha e in.gov.br — o design de fallback (FR-003) nunca consulta as duas na mesma
  execução, então esse cenário não pode ocorrer.
- FR-012/FR-014 (idempotência e respeito à pausa) valem para os três tipos de envio — cada história
  tem seu próprio par de testes (T023/T025 em US1, T036/T037 em US2, T047/T048 em US3) em vez de
  assumir que a garantia de uma fase cobre as outras.
- Parar em qualquer checkpoint acima já entrega valor de forma independente e testável.
