# Tasks: Endurecimento da resolução de processo no SEI/CADE

**Input**: Design documents from `/specs/008-endurecer-scraper-sei/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/process-resolution.md, quickstart.md

**Tests**: incluídos — a constituição do projeto exige testes com fixtures HTML locais para
scrapers/extractors (Princípio VII / Development Workflow item 3).

**Organization**: tarefas agrupadas por história de usuário (US1/US2/US3 do spec.md), na mesma
ordem de prioridade.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: história de usuário à qual a tarefa pertence
- Caminhos de arquivo exatos em cada descrição

---

## Phase 1: Setup

**Purpose**: preparar nomes/constantes compartilhados pelas três estratégias de busca. Não há
dependência nova nem estrutura de projeto a criar (reaproveita `apps/monitoring/` já existente).

- [X] T001 [P] Adicionar constantes com os nomes dos campos do formulário de busca do SEI em
  `apps/monitoring/extractors.py` (`SEARCH_FIELD_PROTOCOLO = 'txtProtocoloPesquisa'`,
  `SEARCH_FIELD_TEXTO = 'txtTextoPesquisa'`, `SEARCH_FIELD_DOCUMENTO = 'txtNumeroDocumentoPesquisa'`),
  para as três estratégias referenciarem os mesmos nomes em vez de strings soltas repetidas.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: hoje `lookup_process_url` e `_fetch_by_process_number` duplicam a mesma lógica de
resolução (cada um faz sua própria única tentativa via campo de protocolo). Esta fase unifica os
dois num único ponto de extensão, **sem mudar nenhum comportamento observável ainda** — é a base
sobre a qual US1/US2/US3 são construídas.

**⚠️ CRITICAL**: nenhuma história de usuário começa antes desta fase terminar.

- [X] T002 Em `apps/monitoring/clients.py`, extrair um helper interno único
  `_resolve_process_detail(process_number: str, timeout: int, user_agent: str) -> tuple[str | None, bytes, int, str]`
  (retorna a URL de detalhe encontrada — ou `None` — mais os `raw, status, charset` da última
  resposta, para o snapshot de fallback) que substitui a lógica hoje duplicada em
  `lookup_process_url` e em `_fetch_by_process_number`. Nesta tarefa o comportamento deve
  permanecer **idêntico** ao atual (uma única tentativa via campo de protocolo) — é um refactor
  comportamento-preservado. **Toda requisição HTTP feita dentro deste helper (nesta e nas fases
  seguintes) MUST passar por `_open_request` — nunca chamar `urllib.request.urlopen` diretamente —
  para preservar a política de retry/backoff já existente (FR-007).** Atualizar
  `lookup_process_url` e `_fetch_by_process_number` para usar esse helper.
- [X] T003 [P] Adicionar teste de regressão em `tests/test_monitoring.py` (mock de
  `apps.monitoring.clients.urllib.request.urlopen`, seguindo o padrão já usado em
  `NativeSeiDocumentTest`) confirmando que `lookup_process_url` e `get_snapshot` (por número de
  processo) continuam retornando exatamente o mesmo resultado de antes do refactor de T002.

**Checkpoint**: `python manage.py test apps.monitoring apps.telegram_bot` passa integralmente com
o comportamento inalterado antes de iniciar qualquer história de usuário.

---

## Phase 3: User Story 1 - Processo só é achado por busca alternativa (Priority: P1) 🎯 MVP

**Goal**: quando a busca por campo de protocolo não encontra o link de detalhe, o sistema tenta
automaticamente a busca por texto livre e depois por número de documento, antes de desistir.

**Independent Test**: mockar a resposta pública do SEI de forma que só a 2ª ou 3ª tentativa
retorne um link de detalhe válido, e confirmar que `resolve_process_url`/`lookup_process_url`/
`get_snapshot` encontram o processo mesmo assim.

### Tests for User Story 1

- [X] T004 [P] [US1] Teste em `tests/test_monitoring.py`: payload de protocolo não resolve, payload
  de texto livre resolve → `_resolve_process_detail`/`lookup_process_url` retornam a URL de
  detalhe esperada.
- [X] T005 [P] [US1] Teste em `tests/test_monitoring.py`: payloads de protocolo e de texto livre
  não resolvem, payload de número de documento resolve → mesmo resultado esperado.
- [X] T006 [P] [US1] Teste em `tests/test_monitoring.py`: página de resultado cita dois processos
  diferentes na mesma resposta → `extract_process_detail_url(html, process_number)` escolhe o
  link da linha de tabela que cita o número do processo pesquisado, não o primeiro link da página.
- [X] T007 [P] [US1] Teste em `tests/test_monitoring.py`: nenhuma das três estratégias resolve →
  `resolve_process_url` retorna `None` e `get_snapshot` cai no snapshot de fallback da própria
  página de pesquisa, exatamente como hoje (sem lançar `FetchError`).

### Implementation for User Story 1

- [X] T008 [US1] Atualizar `extract_process_detail_url` em `apps/monitoring/extractors.py` para
  `extract_process_detail_url(html: str, process_number: str | None = None) -> str | None`:
  quando `process_number` é informado, procurar primeiro um link de detalhe dentro de uma linha
  `<tr>...</tr>` cujo texto cite esse número (comparação por dígitos, ignorando formatação);
  quando omitido, manter o comportamento atual (primeiro link da página). *(depende de T002)*
- [X] T009 [US1] Em `apps/monitoring/clients.py`, adicionar
  `_build_search_payload_attempts(process_number: str, user_agent: str) -> list[dict[str, str]]`
  gerando os três payloads em sequência (protocolo; texto livre; +nº de documento), usando as
  constantes de T001 e reaproveitando os campos hoje fixos em `_build_search_request` como base
  comum. *(depende de T001)*
- [X] T010 [US1] Atualizar `_resolve_process_detail` (T002) para iterar
  `_build_search_payload_attempts` (T009), enviando cada POST em sequência (via `_open_request`,
  conforme já exigido em T002) e chamando `extract_process_detail_url(html, process_number)` (T008)
  após cada resposta, retornando no primeiro sucesso; preservar o retorno de fallback (dados da
  última tentativa) quando nenhuma resolver. *(depende de T008, T009)*

**Checkpoint**: US1 completo e testável isoladamente — processos que hoje só resolveriam pela
busca por texto livre ou por número de documento passam a ser encontrados.

---

## Phase 4: User Story 2 - Número de processo digitado com zero a mais (Priority: P2)

**Goal**: um número de processo com um zero a mais no início do primeiro bloco de dígitos é
corrigido automaticamente antes de qualquer busca.

**Independent Test**: chamar a resolução de processo com o número com zero a mais e confirmar que
o resultado é idêntico ao de pesquisar com o número correto.

### Tests for User Story 2

- [X] T011 [P] [US2] Teste unitário de `normalize_cade_process_number` em
  `tests/test_monitoring.py`: zero a mais no início é removido; número já no formato correto não
  muda; string fora do formato esperado não é alterada.
- [X] T012 [P] [US2] Teste em `tests/test_monitoring.py`: resolver um processo com zero a mais no
  número produz o mesmo resultado (mesma URL de detalhe) que resolver com o número correto, usando
  o mesmo mock de resposta HTML para os dois casos.

### Implementation for User Story 2

- [X] T013 [US2] Implementar `normalize_cade_process_number(value: str) -> str` em
  `apps/monitoring/extractors.py`.
- [X] T014 [US2] Chamar `normalize_cade_process_number` (T013) no início de
  `_resolve_process_detail` (T002), antes de montar qualquer payload de busca. *(depende de T002,
  T013)*

**Checkpoint**: US2 completo — número com zero a mais resolve igual ao número correto, sem afetar
o comportamento de números já corretos.

---

## Phase 5: User Story 3 - Formulário público do SEI muda um campo oculto (Priority: P3)

**Goal**: os valores padrão atuais dos campos ocultos do formulário de pesquisa são lidos via GET
antes de montar qualquer busca, em vez de depender de uma lista fixa no código.

**Independent Test**: simular uma página de pesquisa com um campo oculto adicional (nome/valor não
previstos no payload fixo atual) e confirmar que esse campo é enviado na requisição POST.

### Tests for User Story 3

- [X] T015 [P] [US3] Teste de `extract_input_defaults` em `tests/test_monitoring.py`: HTML com
  vários `<input name=... value=...>` retorna o dicionário `name -> value` esperado; HTML sem
  `<input>` retorna dicionário vazio, sem lançar exceção.
- [X] T016 [P] [US3] Teste em `tests/test_monitoring.py`: página de pesquisa simulada com um campo
  oculto novo (não previsto no payload fixo atual) → o payload da requisição POST enviada inclui
  esse campo com o valor lido da página.
- [X] T017 [P] [US3] Teste em `tests/test_monitoring.py`: a requisição GET inicial (leitura dos
  defaults do formulário) falha por rede/timeout (mock de `urlopen` levantando `URLError`/
  `TimeoutError`) → o erro propaga como `FetchError` (via `lookup_process_url`), sujeito à mesma
  política de retry/backoff de `_open_request` (T002) — não trava nem é silenciado.

### Implementation for User Story 3

- [X] T018 [US3] Implementar `InputDefaultsParser` (subclasse de `html.parser.HTMLParser`) e
  `extract_input_defaults(html: str) -> dict[str, str]` em `apps/monitoring/extractors.py`,
  capturando `name`/`value` de cada `<input>` do formulário.
- [X] T019 [US3] Atualizar `_resolve_process_detail` (T002) para fazer uma requisição GET inicial
  em `CADE_SEARCH_URL` (via `_open_request`, conforme já exigido em T002), extrair os defaults via
  `extract_input_defaults` (T018) e usá-los como base de cada payload, sobrescrita pelos campos que
  as tentativas de US1 (T009) e a normalização de US2 (T014) já controlam. *(depende de T002, T009,
  T018)*

**Checkpoint**: US3 completo — uma mudança de campo oculto no formulário do SEI não quebra a
resolução de processo, sem precisar de alteração de código.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T020 Rodar `python manage.py test apps.monitoring apps.telegram_bot` e confirmar toda a
  suíte (existente + nova) passando (quickstart.md, passo 1).
- [X] T021 Validar manualmente contra o SEI real seguindo `quickstart.md` passo 2 (uso econômico do
  endpoint público — cada cenário só precisa ser checado uma vez).
- [X] T022 [P] Revisar a docstring de módulo em `apps/monitoring/clients.py` (topo do arquivo) e
  atualizá-la se o texto atual não refletir mais a estratégia de múltiplas buscas.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências — pode começar imediatamente.
- **Foundational (Phase 2)**: depende de T001; bloqueia todas as histórias de usuário.
- **User Story 1 (Phase 3)**: depende só da Foundational — pode ser entregue sozinha como MVP.
- **User Story 2 (Phase 4)**: depende só da Foundational (T002). Não depende de US1, mas
  compartilha o mesmo ponto de extensão (`_resolve_process_detail`).
- **User Story 3 (Phase 5)**: depende da Foundational (T002) **e** de T009 (US1), porque a base do
  payload que os defaults dinâmicos alimentam é a mesma lista de tentativas criada em US1. Os
  testes T015-T017 não dependem de US1, mas a integração final (T019) precisa de T009 já existir.
- **Polish (Phase 6)**: depende de todas as histórias desejadas estarem completas.

### Parallel Opportunities

- T001 (Setup) não depende de nada e pode começar já.
- Dentro da Foundational: T003 pode rodar em paralelo assim que T002 terminar.
- Todos os testes de uma mesma história marcados `[P]` (T004-T007, T011-T012, T015-T017) podem ser
  escritos em paralelo entre si.
- US1 e US2 podem ser implementadas em paralelo por pessoas diferentes assim que a Foundational
  terminar (ambas mexem em `_resolve_process_detail`, então exigem coordenação de merge, mas não
  têm dependência lógica uma da outra).
- US3 só pode começar sua tarefa de integração (T019) depois de US1 (T009) estar pronta.

---

## Implementation Strategy

### MVP First (User Story 1)

1. Completar Setup (T001) e Foundational (T002-T003).
2. Completar User Story 1 (T004-T010).
3. Rodar `python manage.py test apps.monitoring apps.telegram_bot` e validar
   `quickstart.md` passo 2.1/2.3.
4. Esse já é o ganho mais caro (spec.md: User Story 1 é P1 porque é o caminho crítico do produto).

### Incremental Delivery

1. Setup + Foundational → base pronta, comportamento inalterado.
2. US1 → processos resolvidos por texto/nº de documento passam a funcionar (MVP).
3. US2 → número com zero a mais passa a resolver.
4. US3 → resiliência a mudança de campo oculto do SEI.
5. Polish → suíte completa + validação manual.

---

## Notes

- Nenhuma dependência nova de runtime é introduzida (Princípio VIII); todos os testes usam
  fixtures HTML inline e mock de `urllib.request.urlopen`, sem chamada HTTP real (Princípio VII).
- Toda requisição HTTP passa por `_open_request` (retry/backoff existente) — ver nota em T002.
- `resolve_process_url`, `lookup_process_url` e `get_snapshot` mantêm a mesma assinatura em todas
  as fases — nenhum chamador externo (`apps/telegram_bot/actions.py`,
  `apps/processes/services.py`, `management/commands/resolve_process.py`) precisa mudar.
- Parar em qualquer checkpoint acima já entrega valor de forma independente e testável.
