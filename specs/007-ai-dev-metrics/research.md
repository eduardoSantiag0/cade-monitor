# Research: Métricas de desenvolvimento assistido por IA

Pesquisa feita em 2026-09-23 sobre as 6 transcrições reais do projeto em
`~/.claude/projects/<slug>/` (Claude Code 2.1.280), lendo apenas **estrutura e números**, nunca
conteúdo. Nada aqui copia texto de conversa.

## R1. Linguagem e execução

- **Decisão**: Python ≥ 3.11 com stdlib; `python -m tools.ai_metrics <comando>` da raiz.
- **Por quê**: o projeto já é Python (3.11 local, 3.12 na imagem/CI); spec exige só biblioteca padrão.
- **Alternativas**: script solto em `scripts/` (só há `.sh` ali; sem estrutura para testes);
  pacote instalável com `pyproject` (fricção sem ganho).

## R2. Onde mora o código

- **Decisão**: `tools/ai_metrics/`, testes em `tools/ai_metrics/tests/` (`unittest`).
- **Por quê**: `manage.py test tests` é o comando do CI e só olha `tests/`; a ferramenta não deve
  ser descoberta por ele nem entrar na imagem (`.dockerignore`). `apps/` é reservado a apps Django.
- **Alternativas**: `scripts/` (misturaria com keepalive); `tests/` (o CI de produção passaria a
  rodar testes da ferramenta).

## R3. Formato das transcrições (verificado)

Cada linha é um JSON. Tipos relevantes:

| Tipo | Campos usados |
|------|---------------|
| `assistant` | `message.id`, `message.model`, `message.usage` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens_details.thinking_tokens`), `message.stop_reason`, blocos `tool_use` (`id`, `name`, `input`), `timestamp`, `effort`, `gitBranch`, `sessionId`, `uuid`, `isSidechain` |
| `user` | prompt humano: `origin.kind == "human"`, conteúdo string, `promptId`, `timestamp`; resultado de ferramenta: bloco `tool_result` (`tool_use_id`, `is_error`) |
| `system` (`subtype: turn_duration`) | `durationMs`, `parentUuid`, `timestamp` |
| `permission-mode` | `permissionMode` (ex.: `auto`) |
| `cost-state` | por sessão: `modelUsage[modelo]` com tokens por tipo, `totalAPIDuration`, `totalToolDuration`, `totalDuration`, `totalLinesAdded/Removed` (e `totalCostUSD`, **ignorado**) |

Achados que moldam o desenho:

1. **Dedupe**: 492 linhas de assistente = 195 respostas únicas (sessão da 006). Em 432 respostas
   repetidas, `usage` foi idêntico em 100% dos casos ⇒ contar por `message.id` e tomar qualquer linha.
2. **Ferramentas ficam espalhadas**: cada linha traz um bloco; a lista de ferramentas de uma
   resposta é a **união** das linhas com o mesmo `message.id`.
3. **Sem código de saída**: o `toolUseResult` de `Bash` traz `stdout/stderr/interrupted`; falha
   aparece só como `is_error: true` no `tool_result`. Verificação verde = `is_error` ausente.
4. **Divergência do custo**: `cost-state` (cumulativo por sessão) difere do somado por
   `message.id`: 006 → cache-read 61,1 M vs 63,4 M (−3,6%), saída 274.193 vs 274.462 (−0,1%);
   005 → cache-read 103,3 M vs 104,8 M (−1,5%). `cost-state` inclui **Haiku** (chamadas auxiliares)
   que nunca aparecem como `assistant` na transcrição. ⇒ divergência medida e lacuna, não igualdade.
5. **Slash commands** aparecem como `<command-name>/speckit-plan</command-name>` no conteúdo do
   prompt (também `/grill-me`, `/model`). Só o **nome** é guardado.
6. **Sem subagentes observados**: `isSidechain` é `false` em todas as 6 transcrições e não há
   pasta `subagents/`. Se surgir `isSidechain: true`, os turnos entram normalmente com a marca e
   o relatório avisa que a origem não foi validada.
7. `gitBranch` por linha permite ver troca de branch dentro de uma sessão (a sessão da 006
   passou por `main`, `005-postgres-render`, `006-telegram-bot`).
8. Não há chamadas da ferramenta `Skill` nas transcrições observadas; o rótulo de workflow vem de
   `<command-name>` e, se existir, de `tool_use` com `name == "Skill"`.

## R4. Disparo automático (hook `Stop`)

- **Decisão**: hook `Stop` chama `python -m tools.ai_metrics ingest --hook`, configurado em
  `.claude/settings.local.json` (local, não versionado). O comando **ignora o conteúdo do stdin**
  e varre todas as transcrições do projeto; é idempotente e sempre sai com código 0.
- **Por quê**: o formato da entrada do hook no Windows é o item **não verificado** da spec. Ao
  não depender dele, o risco some. Ganho adicional: recupera sessões perdidas por hooks anteriores.
- **Verificado (T024, 2026-09-23, Claude Code 2.1.281, Windows)**: o hook `Stop` instalado pelo `setup` **dispara de
  verdade**, inclusive numa sessão já aberta (o Claude Code recarregou o `settings.local.json`), a cada fim de turno.
  O comando roda em bash com o diretório de trabalho = raiz do projeto, e com exit 0, sem saída e independente do cwd
  também pelo `cmd.exe`. O stdin é um JSON com `session_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `prompt_id`,
  `permission_mode`, `effort`, `hook_event_name` (`Stop`), `stop_hook_active`, `last_assistant_message` (**texto da
  resposta**: mais um motivo para a ferramenta ignorar o stdin), `background_tasks` e `session_crons`. O stdin vem em
  UTF-8, enquanto o `sys.stdin` do Python no Windows usa cp1252 por padrão: só importaria se a ferramenta o lesse.
  A captura pelo hook foi confirmada pelo crescimento do histórico (`verify` OK, `errors.log` vazio). PowerShell não
  aceita uma string entre aspas como comando: se o Claude Code passar a executar hooks em PowerShell, o `setup`
  precisará escrever `& "..."`; hoje não é o caso.
- **Alternativas**: ler `transcript_path` do stdin (depende do formato); ingestão só manual
  (perde dados se o usuário esquecer).

## R5. Retenção de transcrições

- **Não verificado** localmente: a documentação do Claude Code cita `cleanupPeriodDays`
  (padrão 30 dias) apagando sessões antigas; o `~/.claude/settings.json` do dono não o define.
- **Decisão**: o hook a cada turno + `ingest` manual são a mitigação. Um comando manual
  `gap add` registra lacunas conhecidas (`transcript-missing`). Não há como detectar
  automaticamente uma sessão que sumiu antes de ser capturada.

## R6. Histórico encadeado (FR-005/FR-006)

- **Decisão**: cada linha é um JSON canônico (chaves ordenadas, sem espaços) com
  `seq`, `ts`, `type`, `prev`, `hash`, `data`; `hash = sha256(canonical(record sem "hash"))`,
  `prev` = `hash` do registro anterior (`"0"*64` no primeiro). `head.json` guarda `{seq, hash}`
  do último registro, para detectar **truncamento**.
- **Verify**: percorre o arquivo recalculando; reporta a primeira `seq` com hash/`prev`/sequência
  inconsistente; compara o final com `head.json`. Se `head.json` está **uma** posição atrás
  (queda entre anexar e atualizar a âncora), corrige a âncora em vez de acusar adulteração.
- **Limite honesto**: é evidência de adulteração, não prova (quem edita o arquivo **e** o
  `head.json` recalculando tudo passa). Documentado nas Limitações do relatório.
- **Alternativas**: HMAC com segredo (gestão de chave sem ganho para uso solo); sem hash
  (não detecta edição).

## R7. Concorrência (FR-010b)

- **Decisão**: arquivo de trava `wal.lock` criado com `os.open(..., O_CREAT|O_EXCL)`, com
  repetição por até 5 s e limpeza de trava com mais de 60 s (processo morto). Se não obtiver a
  trava, o modo hook sai com 0 e registra em `errors.log`; a próxima captura recupera tudo.
- **Alternativas**: `msvcrt.locking`/`fcntl` (código por SO); `sqlite3` como WAL (fora da
  restrição: o histórico é `.jsonl`).

## R8. Idempotência e transcrição incompleta

- **Decisão**: o estado de "já capturado" é reconstruído do próprio histórico (conjunto de
  `msgId` e de `uuid` de prompts/`turn_duration`). `state.json` guarda só `{arquivo: [tamanho, mtime_ns]}`
  para pular arquivos sem mudança (otimização; apagar `state.json` é seguro).
- Uma resposta só é gravada quando **completa**: todos os `tool_use` dela têm `tool_result`, ou
  ela não é a última do arquivo, ou o modo é `--hook`/`--final`. Isso evita gravar uma resposta
  com lista de ferramentas parcial durante uma ingestão manual no meio do turno.

## R9. Validação contra `cost-state` (FR-003)

- **Refinamento (dados reais, 2026-09-23)**: o tipo `in` (tokens de entrada sem cache) diverge 60–100% mas vale
  ~0,001% do total; por isso só geram **aviso** os tipos com ≥ 1% dos tokens do modelo (`MATERIAL_SHARE`).
  A lacuna `unlogged-api-calls` continua sendo registrada para qualquer divergência positiva.
- **Decisão**: por sessão, comparar por modelo e tipo a soma capturada com o **último**
  `cost-state` (é cumulativo). Evento `session.cost` guarda os totais informados (sem USD) só se
  mudaram. A divergência é `(informado − capturado) / informado`. Acima do limite (padrão 5% por
  tipo, modelo com maior volume) → aviso no relatório; qualquer divergência positiva vira
  `coverage.gap` com `source: "unlogged-api-calls"` (não recuperável).
- Modelos que só aparecem no `cost-state` (Haiku) entram como parte da lacuna, não como turnos.

## R10. Nascimento, rascunhos e situação da feature

- **Nascimento**: ao ver um `gitBranch` novo (≠ `main`/`master` e não derivado — R10b), grava
  `feature.born` com `bornAt` = criação no reflog do branch (`git reflog show --date=iso
  <branch>`, entrada "branch: Created from") ou, na falta, o primeiro turno naquele branch.
  Congelar no histórico evita depender do reflog (que expira).
- **R10b – branch derivado**: um branch criado a partir de um branch de feature (hook do Spec
  Kit) é ignorado se, no reflog, "Created from" aponta para outro branch de feature.
- **Alias**: primeira leitura/escrita em `specs/NNN-*/` durante turnos de uma feature ativa
  gera `feature.alias` (`source: "spec-created-on-active-branch"` quando o diretório foi
  **criado** — `Write` em `spec.md` — e `"path-evidence"` caso contrário).
- **Rascunho**: turnos em `main`/`master` (ou sem branch) sem evidência de caminho formam um
  rascunho por sessão. Vincula-se à feature cujo `bornAt` cai em `[início, fim + 30 min]` do
  rascunho (folga configurável `draft_link_grace_minutes`). Achado real: a conversa de setup
  terminou 18:36:12 e o branch nasceu segundos depois; sem folga o vínculo falharia.
- **Situação**: entregue se o branch é ancestral de `main` (`git merge-base --is-ancestor`), ou
  se um commit de merge em `main` cita o nome do branch (branch apagado); abandonada se sem
  atividade por `abandon_after_days` (30) e não integrada; senão em andamento. Merge com
  squash e branch apagado não é detectável: o dono declara por `feature status`.
- **Ordem de atribuição** (FR-015 ajustado): (1) `attribution.set/corrected` mais recente;
  (2) o turno ocorreu no branch da feature ou de um alias; (3) evidência de caminho
  (`specs/NNN-*`); (4) `unattributed`. O `gitBranch` é evidência de "inferred", coerente com a
  US3 cenário 1 (a spec listava só caminho, o que contradizia esse cenário).

## R11. Nome do bot do Telegram (Princípio V)

- **Decisão**: guarda de escrita. Antes de gravar qualquer linha do histórico ou de um relatório,
  se `TELEGRAM_BOT_USERNAME` existir no ambiente ou no `.env` da raiz, o valor é procurado (sem
  distinção de maiúsculas) no texto; se aparecer, a escrita é recusada e o evento é descartado
  com aviso genérico que **não** repete o valor. O valor nunca é gravado, logado nem exibido.
- Testes usam o placeholder `ExemploBot`.
- **Alternativa**: confiar que nada de texto é gravado (já é regra), mas caminhos e nomes de
  branch poderiam conter o nome; a guarda cobre esse buraco.

## R12. O que não entra no histórico (privacidade)

- **Comandos `Bash` e `PowerShell` não são gravados.** O comando é classificado no ingest e só o resultado da
  classificação fica: `verify: {id, ok}` se casa com um comando de verificação da configuração,
  `git: "commit" | "merge" | ...` se for operação git relevante (usa também `toolUseResult.gitOperation`).
  Motivo: comandos com heredoc carregam conteúdo de arquivo.
- **Caminhos**: gravados relativos à raiz do repositório; fora dela vira `{"outside": true}`.
- **Linhas escritas** por chamada (`add`/`del`) são **contagens** calculadas de `Edit`
  (`old_string`/`new_string`) e `Write` (`content`); o conteúdo é descartado.
- **Prompts**: só `ts`, `promptId`, `uuid`, nome do slash command e a classe dos argumentos
  (`none` | `task-range` | `other`, por regex `T\d{3}`), nunca o texto.

## R13. Análise por LLM (FR-044..049)

- **Decisão**: `subprocess.run(["claude", "-p", "--output-format", "json", "--model", <m>], input=<prompt>, cwd=~/.cade-metrics/analysis-cwd)`.
  O prompt embute o JSON de fatos e métricas ([contracts/analysis-io.md](contracts/analysis-io.md)). Sem
  acesso a transcrições nem ao repositório (cwd vazio fora do repo).
- **Sobrecarga**: a transcrição dessa execução cai em `~/.claude/projects/<slug do analysis-cwd>/`,
  varrida pelo `ingest` e classificada `analysis-overhead` **pela origem** (cwd da sessão =
  `analysis-cwd`). Nunca entra em feature, nem na ativa; é somada à parte no relatório de
  "Sobrecarga de análise".
- **Validação** em código: esquema JSON, IDs de métrica existentes, números iguais aos
  calculados, regex de linguagem causal (`causou|causa|reduziu|reduz|porque|por causa de|devido a|levou a|resultou em`),
  toda afirmação com ≥ 1 evidência. Uma tentativa; sem reparo automático.
- **Verificado (T057, Claude Code 2.1.281, Windows)**: `claude -p --output-format json --tools "" --disable-slash-commands`
  lendo o prompt do stdin funciona. A saída é um único JSON com `result` (string com o texto do modelo),
  `is_error`, `num_turns`, `session_id`, `usage`, `modelUsage` e `total_cost_usd` (este último é **ignorado**:
  a ferramenta só usa `result`). `--tools ""` desliga todas as ferramentas; `--model` escolhe o modelo. Não existe
  `--max-turns` nesta versão: sem ferramentas o run tem 1 turno. A transcrição da execução é gravada em
  `~/.claude/projects/<slug do cwd>/` (slug = caracteres não alfanuméricos → `-`), o que confirma a
  classificação `analysis-overhead` pela pasta de origem.

## R14. Onde o hook é instalado

- **Decisão (aprovada)**: `.claude/settings.local.json` (arquivo local, fora do que se publica),
  configurado por um comando único `python -m tools.ai_metrics setup` (contrato em
  [contracts/cli.md](contracts/cli.md)). O `setup` **mescla** a entrada `hooks.Stop` no JSON
  existente (preserva as demais chaves, cria o arquivo se faltar, é idempotente e faz cópia de
  segurança `.bak` antes de alterar) e escreve o comando com o caminho **absoluto** do Python
  (`sys.executable`) e do `__main__.py`, para não depender do diretório de trabalho do hook.
  O `__main__.py` insere a raiz do repositório no `sys.path` quando executado por caminho.
- **Alternativa**: `.claude/settings.json` versionado (impõe o hook a quem clonar o repo, e o
  projeto é público).

## R15. Configuração padrão

Valores padrão em `config.default.json` (versionado); sobrescrita opcional em
`~/.cade-metrics/config.json`. Detalhes em [contracts/config.md](contracts/config.md).
Backfill de 005/006: janelas por commit (`6d098f9` → `95dbc2a` para a 006; a 005 termina em
`6d098f9`) e as sessões em `~/.claude/projects` cobrem 22/09 (005 e 006 na mesma sessão
`9b8e7344`, com troca de `gitBranch`); a atribuição por `gitBranch` **e** por caminho
funciona para as duas.
