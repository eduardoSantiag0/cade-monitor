# Data Model: Métricas de desenvolvimento assistido por IA

Duas camadas, separadas de propósito (FR-009):

1. **Fatos e eventos** — gravados no histórico, imutáveis. Formato em
   [contracts/wal-events.md](contracts/wal-events.md).
2. **Derivados** — calculados a cada relatório a partir dos eventos (+ Git). Nada disto é gravado.

## 1. Entidades gravadas (eventos)

| Evento | Camada | Representa | Campos principais |
|--------|--------|-----------|-------------------|
| `turn` | fato | Uma resposta do assistente (unidade de custo) | `msgId`, `sessionId`, `uuid`, `ts`, `model`, `effort`, `permissionMode`, `gitBranch`, `usage{in,out,cacheRead,cacheCreate,thinking}`, `stop`, `tools[]`, `sidechain`, `source` |
| `prompt` | fato | Início de um ciclo (prompt humano) | `sessionId`, `uuid`, `promptId`, `ts`, `gitBranch`, `skill?`, `argsKind` |
| `turn.end` | fato | Fim de um ciclo | `sessionId`, `uuid`, `ts`, `durationMs` |
| `session.cost` | fato | Totais por modelo informados pela ferramenta (sem USD) | `sessionId`, `ts`, `models{modelo:{in,out,cacheRead,cacheCreate,thinking}}`, `apiMs`, `toolMs`, `totalMs`, `linesAdded`, `linesRemoved` |
| `context.event` | fato | Compactação ou `/clear` | `sessionId`, `ts`, `kind` |
| `feature.born` | fato | Nascimento de uma feature | `featureId`, `bornAt`, `bornSource`, `dataClass`, `coverage`, `window?` |
| `feature.alias` | atribuição | Nome alternativo | `featureId`, `alias`, `source` |
| `attribution.set` | atribuição | Declaração explícita (feature, workflow, marca) | `featureId`, `scope`, `workflow?`, `tag?`, `reason` |
| `attribution.corrected` | atribuição | Correção de atribuição anterior | `corrects` (`seq`), + campos de `attribution.set` |
| `status.corrected` | atribuição | Declara entregue/abandonada/em andamento | `featureId`, `status`, `reason` |
| `firstPass.corrected` | atribuição | Corrige o ciclo de first-pass | `featureId`, `cycleUuid` ou `unknown` |
| `coverage.gap` | fato | Lacuna de medição | `source`, `from`, `to`, `reason`, `recovered`, `featureId?` |
| `analysis.generated` | fato | Uma análise por LLM | `featureId`, `model`, `promptVersion`, `inputHash`, `outputHash`, `accepted`, `reportFile` |

**Chave de identidade** de fatos: `turn` = `msgId`; `prompt` = `uuid`; `turn.end` = `uuid`;
`session.cost` = `(sessionId, hash dos totais)`. É isso que torna a captura idempotente (FR-002).

`tools[]` (dentro de `turn`), um item por chamada de ferramenta:

| Campo | Tipo | Regra |
|-------|------|-------|
| `name` | string | Nome da ferramenta (`Read`, `Edit`, `Write`, `Bash`, `Skill`...) |
| `path` | string? | Só `Read`/`Edit`/`Write`; relativo à raiz; ausente se `outside` |
| `outside` | bool? | `true` se o caminho está fora do repositório |
| `add`, `del` | int? | Linhas escritas (só `Edit`/`Write`); `Write` = tudo `add` |
| `verify` | `{id, ok}`? | `Bash` que casa um comando de verificação; `ok = !is_error` |
| `git` | string? | `commit`, `merge`, `push`... (classificado; comando não é gravado) |
| `skill` | string? | Nome da skill (ferramenta `Skill`) |

## 2. Entidades derivadas

### Feature

Identidade = `featureId` (nome do branch). Derivada de `feature.born`.

| Atributo | Fonte |
|----------|-------|
| `aliases` | `feature.alias` |
| `workflow` | Skills nos `prompt`/`tools[].skill` da feature: `speckit-*` → speckit; `grill*` → grill; ambos → `grill+speckit`; nenhum → `direct`. Sobrescreve `attribution.set.workflow`. |
| `status` | `em andamento` \| `entregue` \| `abandonada` (R10; `status.corrected` vence) |
| `dataClass` / `coverage` | `feature.born`; `observed`/`complete` por padrão para features vistas pela captura (as de `history_windows` entram só pelo `backfill`, como `historical`/`partial`); uma lacuna não recuperada **diferente** da sistemática `unlogged-api-calls` torna a cobertura efetiva `partial` |
| `costClass` | `entregue`, `abandonada`, `exploração sem entrega` (rascunho sem feature), `unattributed`; `em andamento` fica fora dos agregados por classe |

Regras de transição de situação: `em andamento → entregue` (integração no branch principal);
`em andamento → abandonada` (30 dias sem atividade, nunca integrada); `abandonada → em andamento`
(voltou a ter atividade). `entregue` só volta por correção manual.

### Atribuição de um turno

Um turno recebe `{featureId | null, mode}` na ordem: `attribution.corrected/set` (mais recente
que cobre o turno; `mode = explicit` ou `corrected`) → `gitBranch` = feature/alias
(`inferred`) → caminho em `specs/NNN-*` de um alias (`inferred`) → rascunho ligado
(`inferred`) → `unattributed`. Turnos com `source: "analysis-overhead"` nunca são atribuídos.

### Rascunho

Sequência de turnos de uma sessão em `main`/`master` sem evidência de caminho. Ligado a uma
feature com `bornAt` em `[início, fim + folga]`; sem ligação = `exploração sem entrega`.

### Ciclo

`prompt` → turnos com mesmo `sessionId` até o próximo `prompt` da sessão. Um ciclo cujos turnos pertencem a
features diferentes (sessão longa que atravessa branches) é dividido em **uma parte por feature**; o prompt
humano fica só na primeira parte atribuída a uma feature (não conta duas vezes) e o tempo das partes divididas
é estimado por timestamps. Campos: `startedAt`,
`endedAt` (do `turn.end`, senão do último turno), `agentCycleSeconds = durationMs/1000`
(fallback: diferença de timestamps, marcado `estimated`), `humanPrompt` (1),
`skill`, `argsKind`, lista ordenada de `tools[]`, `lastVerification` (`ok`/`fail`/`none`),
`hasCommit`.

### Fases

```text
Pré-Implementação : bornAt ..................... turno com 1ª escrita executável (exclusive)
Implementação     : turno da 1ª escrita executável ..... firstPassAt
Pós-First-Pass    : depois de firstPassAt
```

- **Escrita executável** = `Edit`/`Write` com `path` casando `executable_paths` e não casando
  `ignore_paths` (config). `firstProductionCodeWrite` = 1ª escrita que casa `production_paths`.
- **Unidade**: o turno inteiro pertence à fase em que ele começa; sem divisão interna.
- **Sem escrita executável**: a feature fica só em Pré-Implementação e `implementationStartedAt`
  = `unknown` (não `0`).
- **Submétricas de Pré-Implementação** (rótulos, não fronteiras): `specArtifactCost` (turnos com
  escrita em `specs/**`), `grillCost` (ciclos cujo prompt é skill `grill*`), `planningCost`
  (ciclos `speckit-plan`/`speckit-tasks`/plan mode), `other`. Um turno entra em **um** rótulo,
  na ordem `specArtifact` > `grill` > `planning` > `other`.

### First-pass

- **Ciclos de entrega**: se algum ciclo pós-início tem skill `speckit-implement` com
  `argsKind != task-range`, eles são de entrega (`firstPassSource` prefixo `feature-delivery`);
  senão o **primeiro ciclo** após o início é `assumed`.
- `firstPassAt` = fim do primeiro ciclo de entrega com `lastVerification == ok`
  (`verified-green`) ou `hasCommit` (`commit-proxy`); senão `unknown`.
- `cyclesUntilFirstPass` = ciclos do início da implementação até ele, inclusive. `firstPass.corrected`
  substitui o ciclo escolhido (`firstPassSource: "corrected"`).
- Sem indicador binário (FR-029).

### Métricas pós-first-pass e de retrabalho

| Métrica | Cálculo |
|---------|---------|
| `postFirstPassTokens`, `postFirstPassRatio` | Tokens (4 tipos) dos turnos após `firstPassAt`; razão sobre o total da feature |
| `postFirstPassChurn` | Linhas `add+del` das escritas executáveis depois de `firstPassAt` e nº de arquivos já modificados antes que voltaram a ser editados |
| `fixCycles` | Ver regra abaixo |
| `humanTurnsAfterFirstPass` | `prompt`s da feature depois de `firstPassAt` |
| `reeditedFiles` | Arquivos executáveis editados antes e depois de `firstPassAt` |

**Regra de `fixCycles`** (FR-030): percorrer, por ciclo, as chamadas na ordem. Estado
`testPending` liga quando há escrita em `test_paths`, desliga em escrita de produção.
Numa verificação com `ok = false`: se `testPending`, é o vermelho esperado — **não** conta e
`testPending` desliga; senão marca `pendingFail`. Uma escrita executável com `pendingFail` conta
**1 ciclo de correção** e limpa `pendingFail`. Uma verificação verde limpa `pendingFail`.

### Contexto

`contextSize(turn) = in + cacheRead + cacheCreate`. Por feature: `peak`, `mean`, arquivos
distintos lidos (`Read.path`), volume = nº de leituras; `context.event` contados por tipo.

### Tempo

`agentCycleSeconds` somado e por fase. `intercycleGapSeconds` = `startedAt(n+1) − endedAt(n)`,
mostrado por mediana; `idle` ≥ `idle_minutes` (30) fica marcado e fora da mediana "ativa".
Tempo de API/ferramenta só por sessão (`session.cost`).

### Spec (só features com `specs/<alias>/tasks.md`)

- **Plan Path Coverage**: `planned` = caminhos citados no `tasks.md` (`git show` da versão do
  branch); `changed` = arquivos executáveis do diff da feature (`git diff --name-only
  <merge-base>..<ponta ou merge>`); `recall = |planned∩changed|/|planned|`,
  `precision = |planned∩changed|/|changed|`.
- **Spec Changes After Implementation Start**: nº e tokens dos turnos com escrita em `specs/**` após
  `implementationStartedAt`.
- Sem `tasks.md` ou `specs/`: `n/a` (não `0`).

### Cobertura

- `coverage.gap` cobre `[from, to]`. Métrica cujo intervalo (turnos usados) intersecta uma lacuna
  **não recuperada** ganha prefixo `≥`. Lacuna `recovered: true` só aparece nas Limitações.
- Divergência de `session.cost`: lacuna `unlogged-api-calls` sempre não recuperável, ligada às
  sessões da feature; por isso quase toda métrica de tokens sai como limite inferior. Isto é
  esperado e é dito na primeira linha das Limitações.
- `dataClass = historical`, `coverage = partial`: nunca entram em agregações (FR-037/FR-039).
- Elegível para comparação: `observed` + `complete` + situação `entregue` ou `abandonada`. A lacuna sistemática
  `unlogged-api-calls` (divergência pequena e sempre presente) marca os tokens com `≥`, mas **não** torna a feature
  não elegível; qualquer outra lacuna não recuperada (`copilot`, `hook-failed`, `transcript-missing`) torna.

### Análise

Ver [contracts/analysis-io.md](contracts/analysis-io.md). Cada execução aceita ou rejeitada gera
um `analysis.generated`; só as aceitas entram no relatório.

## 3. Restrições de validação

- Todo evento tem `seq` contínuo, `prev`/`hash` válidos.
- Nenhum campo de texto livre, exceto `reason` de eventos manuais (curto, digitado pelo dono,
  sujeito à guarda do nome do bot) e `tag`.
- Nenhum campo monetário: o ingestor descarta `totalCostUSD` e `costUSD` na leitura.
- Timestamps em ISO 8601 UTC como vêm da fonte.
