# Feature Specification: Sugestão de Monitoramento de Processos Relacionados

**Feature Branch**: `003-auto-monitor-processos-relacionados`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Detectar automaticamente processos relacionados/apartados citados nos andamentos de um processo já monitorado e permitir que o usuário aprove rapidamente o monitoramento desses processos relacionados, em vez de precisar cadastrá-los manualmente do zero."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver processos relacionados sugeridos (Priority: P1)

Como usuário do painel, quando um andamento de um processo que já monitoro menciona outro número de processo (ex.: "apartado", "apenso", "encaminhado para o processo X"), quero ver esse número sugerido na tela de detalhe, para não precisar ler manualmente cada andamento em busca de processos relacionados que valeria a pena acompanhar também.

**Why this priority**: É o valor central da feature — sem a detecção e exibição da sugestão, não há nada para aprovar. `apps/monitoring/extractors.py` já identifica essas menções (`related_process_mentions`, `is_relevant_movement`); esta história conecta isso à interface.

**Independent Test**: Pode ser testado cadastrando um processo cujo texto de andamento contenha uma menção a outro número de processo, rodando uma checagem, e confirmando que o número aparece como sugestão na tela de detalhe do processo de origem.

**Acceptance Scenarios**:

1. **Given** um processo monitorado cujo último snapshot contém um andamento mencionando outro número de processo no formato `NNNNN.NNNNNN/AAAA-DD`, **When** o usuário abre a tela de detalhe desse processo, **Then** o número mencionado aparece em uma seção de "processos relacionados sugeridos", desde que esse número ainda não esteja monitorado.
2. **Given** um número de processo mencionado que já está cadastrado como `MonitoredProcess` (em qualquer status), **When** a tela de detalhe é exibida, **Then** esse número NÃO aparece como sugestão — em vez disso, um link direto para o processo já cadastrado pode ser exibido.

---

### User Story 2 - Aprovar uma sugestão com uma ação (Priority: P1)

Como usuário do painel, quero aprovar uma sugestão de processo relacionado com uma única ação, para começar a monitorá-lo sem precisar copiar o número e preencher o formulário de cadastro manualmente.

**Why this priority**: É o que transforma a detecção em valor prático — sem aprovação fácil, a sugestão é só mais uma informação para copiar manualmente, o que o usuário já pode fazer hoje lendo o andamento.

**Independent Test**: Pode ser testado clicando em "monitorar" sobre uma sugestão exibida e confirmando que um novo `MonitoredProcess` é criado com esse número como `source`, seguindo o mesmo fluxo de resolução de URL já usado no cadastro manual.

**Acceptance Scenarios**:

1. **Given** uma sugestão de processo relacionado exibida na tela de detalhe, **When** o usuário aprova a sugestão, **Then** um novo processo monitorado é criado com esse número, e a origem da sugestão (processo e andamento que a geraram) fica registrada para consulta futura.
2. **Given** uma sugestão recém-aprovada, **When** o usuário volta à tela de detalhe do processo de origem, **Then** essa sugestão não aparece mais na lista de pendentes — aparece como "já monitorado", com link para o novo processo.

---

### User Story 3 - Dispensar uma sugestão irrelevante (Priority: P2)

Como usuário do painel, quero poder dispensar uma sugestão que não me interessa (ex.: falso positivo, processo de outra parte sem relevância), para que ela não continue aparecendo a cada nova checagem.

**Why this priority**: Sem essa opção, sugestões irrelevantes acumulam e o usuário passa a ignorar a seção inteira — reduz o valor da história 1. É P2 porque o sistema ainda é útil sem isso (só fica mais barulhento com o tempo).

**Independent Test**: Pode ser testado dispensando uma sugestão e confirmando que ela não reaparece em checagens futuras do mesmo processo, mesmo que a menção continue presente no texto extraído.

**Acceptance Scenarios**:

1. **Given** uma sugestão pendente, **When** o usuário a dispensa, **Then** ela deixa de aparecer na lista de pendentes desse processo, mesmo em checagens futuras.

---

### Edge Cases

- Se o mesmo número relacionado for mencionado em múltiplos andamentos ou mudanças diferentes do mesmo processo de origem, o sistema MUST tratar como uma única sugestão (sem duplicar entradas).
- Se o número sugerido corresponder, na verdade, a um número de documento (não de processo) por coincidência de formato, o usuário precisa conseguir dispensá-lo com a mesma facilidade de qualquer outra sugestão — o sistema não tenta validar semanticamente se é "de fato" um processo relacionado.
- Se o processo sugerido já existir com status `ARCHIVED` ou `PAUSED`, a tela MUST indicar esse estado e oferecer link/reativação em vez de tratar como "ainda não monitorado".
- Aprovar várias sugestões de uma vez não deve furar o intervalo mínimo de checagem (Princípio II da constituição) — cada processo recém-criado entra na fila de checagem normal, sem prioridade especial sobre os demais.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST identificar, a partir do texto já extraído de cada checagem, números de processo mencionados em andamentos relevantes (reutilizando a lógica já existente de `related_process_mentions`/`is_relevant_movement`), sem exigir nenhuma requisição HTTP adicional além da checagem normal já realizada.
- **FR-002**: O sistema MUST NOT criar automaticamente um novo processo monitorado a partir de uma menção detectada — toda criação exige uma ação explícita do usuário. Isso está alinhado ao Princípio VI da constituição (nenhuma ação automática sem confirmação humana) e ao Princípio II (evitar picos de novos processos entrando no ciclo de checagem sem controle).
- **FR-003**: A tela de detalhe de um processo MUST exibir os números de processo mencionados em seus andamentos que ainda não estão monitorados e ainda não foram dispensados para aquele processo de origem.
- **FR-004**: Usuários MUST conseguir aprovar uma sugestão com uma única ação, o que cria um novo processo monitorado usando esse número como `source`, reaproveitando o mesmo fluxo de resolução de URL pública já usado no cadastro manual.
- **FR-005**: Usuários MUST conseguir dispensar uma sugestão, e uma sugestão dispensada MUST NOT reaparecer em checagens futuras do mesmo par (processo de origem, número sugerido).
- **FR-006**: O sistema MUST registrar, para cada processo criado por esta via, de qual processo de origem e de qual andamento/mudança a sugestão partiu, de forma consultável na interface.
- **FR-007**: Um processo criado a partir de uma sugestão aprovada MUST seguir as mesmas regras de intervalo mínimo de checagem e fila de prioridade (`get_due_processes`) que qualquer processo cadastrado manualmente — nenhum tratamento especial que fure o ciclo padrão.
- **FR-008**: Se o número sugerido já corresponder a um processo monitorado existente (em qualquer status), o sistema MUST oferecer um link para o processo existente em vez de permitir uma tentativa de criação duplicada.

### Key Entities

- **RelatedProcessSuggestion**: Representa um número de processo mencionado em um andamento de um processo já monitorado (o "processo de origem"), ainda não monitorado por conta própria. Atributos-chave: processo de origem, número sugerido, andamento/mudança de origem (para rastreabilidade), status (pendente, aprovada, dispensada), data de detecção. Relaciona-se com `MonitoredProcess` (origem) e, quando aprovada, com o novo `MonitoredProcess` criado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A partir da tela de detalhe de um processo com menções detectadas, o usuário consegue começar a monitorar um processo relacionado em no máximo 2 ações (visualizar sugestão + aprovar).
- **SC-002**: Nenhuma sugestão previamente aprovada ou dispensada reaparece como pendente em checagens subsequentes.
- **SC-003**: 100% dos processos criados por esta via entram no ciclo de checagem respeitando o intervalo mínimo padrão, sem checagem imediata fora de fila.
- **SC-004**: A partir de um processo criado por esta via, um revisor consegue identificar em até 1 clique qual processo e andamento originaram a sugestão.

## Assumptions

- A extração de menções a processos relacionados usa a mesma regex/heurística já implementada em `apps/monitoring/extractors.py` (`related_process_mentions`, `is_relevant_movement`); esta spec não introduz uma nova técnica de reconhecimento, apenas conecta a existente à interface e a um fluxo de aprovação.
- Falsos positivos (números capturados que não são, de fato, processos relacionados relevantes) são esperados e tratados via a ação de dispensar (User Story 3), não via detecção perfeita.
- Esta spec não cobre descoberta recursiva (isto é, sugerir processos relacionados a processos que só existem como sugestão pendente) — a sugestão só é gerada a partir de processos já efetivamente monitorados.
- O volume típico de sugestões por processo é baixo (poucas unidades), então nenhuma paginação dedicada é necessária na seção de sugestões da tela de detalhe.
