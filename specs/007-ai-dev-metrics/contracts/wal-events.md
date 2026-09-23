# Contrato: histórico de eventos (`wal.jsonl`)

Arquivo `~/.cade-metrics/wal.jsonl`, UTF-8, uma linha por registro, **só anexa**.

## Envelope

```json
{"seq":42,"ts":"2026-09-23T18:49:54.793Z","type":"turn","source":"claude-code","prev":"<sha256 do registro 41>","data":{...},"hash":"<sha256>"}
```

| Campo | Regra |
|-------|-------|
| `seq` | Inteiro contínuo a partir de 1 |
| `ts` | Momento do **fato** (não da gravação), ISO 8601 UTC |
| `type` | Um dos tipos abaixo |
| `source` | `claude-code`, `manual`, `analysis-overhead`, `git`, `backfill` (`Bash` e `PowerShell` são tratados igual; `MultiEdit` conta linhas de todas as edições) |
| `prev` | `hash` do registro anterior; 64 zeros no primeiro |
| `hash` | `sha256` de `json.dumps(registro sem "hash", sort_keys=True, separators=(",",":"), ensure_ascii=False)` |

`~/.cade-metrics/head.json`: `{"seq": 42, "hash": "..."}` — âncora para detectar truncamento.

## Tipos e `data`

Exemplos com valores fictícios. Campos com `?` são opcionais (ausentes = desconhecido).

### `turn`

```json
{"msgId":"msg_...","sessionId":"...","uuid":"...","model":"claude-opus-5-5","effort":"medium",
 "permissionMode":"auto","gitBranch":"007-ai-dev-metrics","sidechain":false,"stop":"tool_use",
 "usage":{"in":2,"out":335,"cacheRead":28549,"cacheCreate":5814,"thinking":161},
 "tools":[{"name":"Edit","path":"tools/ai_metrics/wal.py","add":12,"del":3},
          {"name":"Bash","verify":{"id":"unit","ok":false}},
          {"name":"Bash","git":"commit"},
          {"name":"Read","outside":true}]}
```

### `prompt`

```json
{"sessionId":"...","uuid":"...","promptId":"...","gitBranch":"...","skill":"speckit-plan","argsKind":"none"}
```

`argsKind`: `none` | `task-range` | `other`. `skill` ausente se não é slash command.

### `turn.end`

```json
{"sessionId":"...","uuid":"...","parentUuid":"...","durationMs":164045}
```

### `session.cost`

```json
{"sessionId":"...","models":{"claude-opus-5-5":{"in":2604,"out":274462,"cacheRead":63412711,"cacheCreate":512018,"thinking":0}},
 "apiMs":2657137,"toolMs":1322077,"totalMs":11382811,"linesAdded":4979,"linesRemoved":581}
```

**Nunca** contém `totalCostUSD`/`costUSD`.

### `context.event`

```json
{"sessionId":"...","kind":"compact"}
```

`kind`: `compact` | `clear`.

### `feature.born`

```json
{"featureId":"007-ai-dev-metrics","bornAt":"2026-09-23T18:36:40Z","bornSource":"reflog",
 "dataClass":"observed","coverage":"complete"}
```

`bornSource`: `reflog` | `first-turn` | `declared`. `dataClass`: `observed` | `historical`.
`coverage`: `complete` | `partial`. Backfill acrescenta `"window":{"from":"...","to":"...","endCommit":"95dbc2a"}`.

### `feature.alias`

```json
{"featureId":"007-ai-dev-metrics","alias":"specs/007-ai-dev-metrics","source":"spec-created-on-active-branch"}
```

`source`: `spec-created-on-active-branch` (criada pelo Spec Kit num branch de feature ativo) | `derived-branch`
(branch criado a partir de um branch de feature: o alias é o nome do branch derivado) | `path-evidence`
(usada pelo `backfill`) | `manual`.

### `attribution.set` / `attribution.corrected`

```json
{"featureId":"007-ai-dev-metrics","scope":{"sessionId":"3fdf02d8-..."},"workflow":"grill","tag":"setup","reason":"conversa de configuração"}
```

`scope`: `{"sessionId": ...}` ou `{"from": ts, "to": ts}` ou `{"turns": [msgId, ...]}`.
`attribution.corrected` traz `corrects: <seq>` e substitui o efeito do registro citado.
`featureId: null` = declarar explicitamente `unattributed`. `tag`: `setup` (excluída de agregados).

### `status.corrected`

```json
{"featureId":"...","status":"entregue","reason":"merge por squash"}
```

`status`: `em andamento` | `entregue` | `abandonada`.

### `firstPass.corrected`

```json
{"featureId":"...","cycleUuid":"<uuid do prompt>","reason":"primeiro ciclo foi parcial"}
```

`cycleUuid: null` = `unknown`.

### `coverage.gap`

```json
{"source":"copilot","from":"2026-09-19T00:00:00Z","to":"2026-09-22T00:00:00Z","reason":"copilot",
 "recovered":false,"featureId":"006-telegram-bot"}
```

`reason`: `copilot` | `hook-failed` | `transcript-missing` | `unlogged-api-calls` | `unreadable-lines`
(linhas ilegíveis no meio de uma transcrição; traz `sessionId` e `lines`). Todas, exceto
`unlogged-api-calls`, tornam a feature inelegível para comparação.
`recovered`: a captura posterior preencheu o intervalo.

### `analysis.generated`

```json
{"featureId":"...","model":"claude-sonnet-5","promptVersion":"1","inputHash":"...","outputHash":"...",
 "accepted":true,"rejectReasons":[],"reportFile":".ai-metrics/reports/007-ai-dev-metrics.md"}
```

## Arquivos auxiliares (não fazem parte da cadeia)

| Arquivo | Conteúdo |
|---------|----------|
| `head.json` | Âncora `{seq, hash}` do último registro reconhecido |
| `state.json` | `{"sizes": {arquivo: [tamanho, mtime_ns]}, "errors_consumed": n}`; só otimização, apagar é seguro |
| `errors.log` | Uma linha por falha do hook: `timestamp<TAB>NÍVEL<TAB>contexto<TAB>mensagem` (NÍVEL ∈ DEBUG, INFO, WARNING, ERROR); linhas `ERROR` viram `coverage.gap` `hook-failed` na captura seguinte; o formato antigo `timestamp<TAB>mensagem` é lido como ERROR |
| `wal.lock` | Trava por `O_EXCL`; uma trava com mais de 60 s é considerada de um processo morto |
| `config.json` | Sobrescrita opcional dos padrões de `config.default.json` |
| `analysis-cwd/` | Pasta vazia, fora do repositório, onde roda o `claude -p` da análise |

## Reparo de cauda interrompida

Se o arquivo termina numa linha sem quebra de linha (queda no meio da gravação) **e** a âncora não reconhece esse
registro, os bytes incompletos são descartados (ou, se o JSON estiver completo, só ganham o `\n`). Se a âncora
reconhece o registro truncado, nada é alterado e o `verify` falha: isso é perda, não queda.

## Invariantes (testáveis)

1. Repetir `ingest` sobre a mesma fonte não cria registros (SC-002).
2. Editar qualquer byte de um registro, remover ou reordenar linhas, ou truncar o final faz
   `verify` falhar e informar a primeira `seq` comprometida (SC-003).
3. Nenhum registro contém texto de prompt/resposta/arquivo/comando, valor monetário ou o
   nome do bot (SC-004).
4. Correções são novos registros; o histórico anterior permanece íntegro (SC-011).
