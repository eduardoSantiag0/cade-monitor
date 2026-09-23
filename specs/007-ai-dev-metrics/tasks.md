---

description: "Task list for 007-ai-dev-metrics"
---

# Tasks: Métricas de desenvolvimento assistido por IA

**Input**: Design documents from `/specs/007-ai-dev-metrics/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (cli, wal-events, analysis-io, config), quickstart.md

**Tests**: **Incluídos.** A constituição (Princípio VII) exige testes automatizados e a spec define critérios verificáveis (SC-001…SC-013). Stack de testes: `unittest` (stdlib), fixtures **sintéticas** (nunca cópias de conversas reais). Em cada fase, os testes vêm antes da implementação e devem falhar primeiro.

**Organization**: Tarefas agrupadas por user story. US1 e US2 (ambas P1) formam o MVP.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: US1…US6 (só nas fases de user story)
- Caminhos relativos à raiz do repositório. Código em `tools/ai_metrics/`, testes em `tools/ai_metrics/tests/`.
- Comando de testes: `python -m unittest discover -s tools/ai_metrics/tests -t .`
- **Regras que valem em todas as tarefas**: nenhum texto de prompt/resposta/conteúdo de arquivo/comando gravado; nenhum valor monetário; UTF-8 explícito em toda leitura e escrita; nunca escrever o nome ou @username reais do bot (usar `ExemploBot` em testes).

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: esqueleto do pacote e regras de ignore (decisão do dono: código versionado; só dados locais ignorados)

- [X] T001 Criar o esqueleto `tools/__init__.py`, `tools/ai_metrics/__init__.py`, `tools/ai_metrics/tests/__init__.py`, `tools/ai_metrics/tests/fixtures/.gitkeep` e `tools/ai_metrics/__main__.py`; o `__main__.py` insere a raiz do repositório em `sys.path` quando executado por caminho de arquivo e chama `cli.main()`
- [X] T002 [P] Adicionar **apenas** `.ai-metrics/` ao `.gitignore` (NÃO ignorar `tools/` nem `tools/ai_metrics/`; o código da ferramenta é versionado)
- [X] T003 [P] Adicionar `.ai-metrics/` e `tools/ai_metrics/` ao `.dockerignore`, para que nem a ferramenta nem seus dados entrem na imagem
- [X] T004 [P] Criar `tools/ai_metrics/config.default.json` com os valores de `specs/007-ai-dev-metrics/contracts/config.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: configuração, histórico encadeado, Git e esqueleto do CLI. Tudo abaixo bloqueia as user stories.

**⚠️ CRITICAL**: nenhuma user story começa antes desta fase terminar.

- [X] T005 [P] Criar `tools/ai_metrics/tests/helpers.py`: construtor de transcrições **sintéticas** (linhas `assistant` com uma linha por bloco e `usage` repetido, `user` humano com `<command-name>`, `tool_result` com/sem `is_error`, `system/turn_duration`, `permission-mode`, `cost-state`), gerador de repositório Git temporário (branches, commits, reflog) e criador de `--home` temporário
- [X] T006 [P] Escrever `tools/ai_metrics/tests/test_wal.py`: envelope (`seq` contínuo, `prev`, `hash` canônico), `verify` detectando edição de um byte, remoção do meio, reordenação e truncamento do final (via `head.json`), reparo quando `head.json` está uma posição atrás, trava por `O_EXCL` com anexadores concorrentes sem duplicar `seq`, limpeza de trava velha, recusa de gravar linha com o valor de `TELEGRAM_BOT_USERNAME` (usar `ExemploBot`) e recusa de campos `totalCostUSD`/`costUSD` (SC-003, SC-004, FR-005, FR-006, FR-010b, FR-004, FR-008)
- [X] T007 Implementar `tools/ai_metrics/config.py`: carrega `config.default.json`, mescla `~/.cade-metrics/config.json`, valida regexes (falha com mensagem clara), ignora chave desconhecida com aviso, e expõe `contains_bot_name(text)` (lê `TELEGRAM_BOT_USERNAME` do ambiente ou do `.env` da raiz, compara sem distinção de maiúsculas, nunca imprime nem grava o valor)
- [X] T008 Implementar `tools/ai_metrics/wal.py` conforme `contracts/wal-events.md`: `append(events)` sob trava, JSON canônico + `sha256`, `head.json`, `read()`, `verify()` (primeira `seq` comprometida; tolera âncora uma posição atrás), rejeição por `contains_bot_name` e por campos monetários, `--home` configurável (faz T006 passar)
- [X] T009 [P] Escrever `tools/ai_metrics/tests/test_gitinfo.py` sobre repositórios temporários: criação do branch no reflog, branch derivado de branch de feature, ancestral de `main`, merge com branch apagado citado no commit de merge, `diff --name-only` entre merge-base e ponta, `git check-ignore`, arquivo em `git show <ref>:<path>`
- [X] T010 Implementar `tools/ai_metrics/gitinfo.py` (subprocess `git`, saída em UTF-8, tempo-limite e erro claro se `git` faltar): `branch_created_at`, `branch_base_sha`, `moved_from`, `is_merged_into`, `merge_commit_for_branch`, `changed_files`, `show_file`, `check_ignored`, `commit_time` (faz T009 passar)
- [X] T011 Implementar `tools/ai_metrics/cli.py` (esqueleto): `argparse` com `--home` e subcomandos (`set_defaults(func=...)`), códigos de saída `0/1/2`, reconfiguração de stdout/stderr para UTF-8, `--help` em português, e o subcomando `verify` (`exit 2` quando `wal.verify()` falha); escrever antes `tools/ai_metrics/tests/test_cli.py` com o teste de `verify` e de `--help`

**Checkpoint**: histórico encadeado, Git e CLI base funcionam; user stories podem começar.

---

## Phase 3: User Story 1 - Registrar o consumo de forma auditável (Priority: P1) 🎯 MVP

**Goal**: captura automática e idempotente do consumo por resposta, sem texto de conversa, com validação contra o total informado pela ferramenta, lacunas registradas e configuração única do hook.

**Independent Test**: com uma sessão sintética, `ingest` grava os eventos; repetir não cria nada; `verify` passa; editar uma linha faz `verify` falhar; `setup` instala o hook sem quebrar o `settings.local.json` existente (quickstart §1–§3).

### Tests for User Story 1 ⚠️ (escrever primeiro; devem falhar)

- [X] T012 [P] [US1] Escrever `tools/ai_metrics/tests/test_ingest.py`: dedupe por `message.id` (492 linhas → 195 turnos no formato sintético), união de `tool_use` de linhas com o mesmo id, idempotência (2ª captura = 0 registros, SC-002), última resposta incompleta adiada sem `--final`, 4 tipos de token + `thinking`, `permissionMode`/`effort`/`gitBranch`, prompt humano só com `promptId`/nome do slash command/`argsKind` (`none`/`task-range`/`other`), `turn.end` a partir de `turn_duration`, `context.event` para compactação e `/clear`, `Bash` classificado como `verify{id,ok}`/`git` **sem gravar o comando**, caminhos relativos (`outside:true` fora do repo), contagem `add`/`del` de `Edit`/`Write` sem conteúdo, `is_error`→`ok:false`, ausência total de `totalCostUSD`/`costUSD` e de texto livre (varredura do histórico, SC-004), `isSidechain` marcado
- [X] T013 [P] [US1] Escrever em `tools/ai_metrics/tests/test_ingest_validation.py`: `session.cost` só quando os totais mudam, divergência por modelo/tipo, aviso acima do limite de 5%, `coverage.gap` `unlogged-api-calls` não recuperável, modelo que só aparece no `cost-state` (Haiku) entra como lacuna e não como turno, sinalização de campo ausente como `unknown` (SC-001, FR-003)
- [X] T014 [P] [US1] Escrever `tools/ai_metrics/tests/test_hook.py`: `ingest --hook` sempre `exit 0` e sem saída mesmo com pasta do histórico ilegível ou trava presa, erro gravado em `errors.log`, próxima captura bem-sucedida grava `coverage.gap` `hook-failed` com `recovered` correto, duas capturas simultâneas (processos) resultam em `verify` ok e sem duplicatas, stdin ignorado (SC-013, FR-010a, FR-010b)
- [X] T015 [P] [US1] Escrever `tools/ai_metrics/tests/test_setup.py`: cria o `settings.local.json` se faltar; mescla só `hooks.Stop` preservando outras chaves e outros hooks `Stop`; cria `.bak`; idempotente (2ª execução sem duplicar); atualiza a entrada própria quando o Python muda; JSON inválido aborta sem alterar; `--dry-run` não grava; `--check` (exit 0/1); `--remove` tira só a entrada da ferramenta; comando gravado usa caminho absoluto do Python e do `__main__.py`; avisa se `.ai-metrics/` não está ignorado; nunca grava dados no repositório fora de `.claude/settings.local.json`

### Implementation for User Story 1

- [X] T016 [US1] Implementar em `tools/ai_metrics/ingest.py` a leitura das transcrições de `~/.claude/projects/<slug do repo>/*.jsonl` (UTF-8, tolerante a linhas inválidas com aviso) e a montagem dos eventos `turn`: dedupe por `message.id`, união das ferramentas, completude (`tool_result` presente, ou não é a última do arquivo, ou `--final`), `usage` nos 4 tipos + `thinking`, modelo, esforço, modo de permissão, branch, `sidechain`, `source: claude-code` (FR-001, FR-002)
- [X] T017 [US1] Em `tools/ai_metrics/ingest.py`, gerar eventos `prompt` (humano: `origin.kind == "human"`; nome do slash command via `<command-name>`; `argsKind` por regex `T\d{3}`), `turn.end` (a partir de `system/turn_duration`) e `context.event` (compactação/`/clear`), sem gravar texto
- [X] T018 [US1] Em `tools/ai_metrics/ingest.py`, implementar a sanitização de ferramentas: caminho relativo à raiz (`outside:true` se fora), `add`/`del` de `Edit`/`Write` (só contagens), `Bash` classificado por `verification_commands`/`git_operations` da config (e por `toolUseResult.gitOperation`) gravando apenas `verify{id,ok}`/`git`, `Skill` → `skill` (FR-007, FR-024)
- [X] T019 [US1] Em `tools/ai_metrics/ingest.py`, implementar `session.cost` (último `cost-state`, ignorando `totalCostUSD`/`costUSD`), o cálculo de divergência por modelo/tipo, o aviso acima do limite configurável e o `coverage.gap` `unlogged-api-calls` (FR-003, FR-004, FR-036)
- [X] T020 [US1] Em `tools/ai_metrics/ingest.py`, implementar `state.json` (`{arquivo: tamanho}`, apagável com segurança), a reconstrução do conjunto "já capturado" a partir do histórico e o resumo de saída (turnos novos, divergência por sessão)
- [X] T021 [US1] Implementar o modo `--hook` em `tools/ai_metrics/ingest.py` e `tools/ai_metrics/cli.py`: ignora o stdin, nunca falha (captura exceções e devolve `0`), erro em `~/.cade-metrics/errors.log`, sem saída, tempo-limite na trava; a próxima captura bem-sucedida consome `errors.log` e grava `coverage.gap` `hook-failed` com `recovered` (FR-010, FR-010a); opção oculta `--dump-stdin <arquivo>` só para o spike
- [X] T022 [US1] Registrar o subcomando `ingest [--hook] [--final] [--quiet]` em `tools/ai_metrics/cli.py` (faz T012–T014 passarem)
- [X] T023 [US1] Implementar `tools/ai_metrics/setup.py` e o subcomando `setup [--dry-run] [--remove] [--check]` conforme `contracts/cli.md`: cria `~/.cade-metrics/`; mescla o hook `Stop` em `.claude/settings.local.json` (cria/`.bak`/idempotente/JSON inválido aborta); comando com `sys.executable` e caminho absoluto do `__main__.py` + `ingest --hook`; confere `git check-ignore .ai-metrics/`; roda uma primeira captura; NÃO roda `backfill` (faz T015 passar)
- [X] T024 [US1] **Spike do hook (R4)**: rodar `setup` de verdade, fechar um turno com `--dump-stdin` ativo uma vez e documentar em `specs/007-ai-dev-metrics/research.md` (seção R4) se o hook dispara, em que diretório e o formato do stdin no Windows; confirmar que o fluxo `git switch -c <feature>` → trabalhar → captura automática funciona sem nenhuma edição manual (SC-005) **Concluída em 2026-09-23**: o hook dispara em sessão aberta, roda no diretório do projeto e o stdin foi documentado em `research.md` (R4); o arquivo de dump (que continha texto da resposta) foi apagado e o `setup` regravou o comando sem `--dump-stdin`.

**Checkpoint**: US1 completa — captura, integridade, hook e setup validados (quickstart §0–§3).

---

## Phase 4: User Story 2 - Ver o relatório de uma feature (Priority: P1) 🎯 MVP

**Goal**: relatório Markdown por feature (Fatos → Métricas → Análise → Evidências → Limitações) com fases, first-pass, retrabalho, contexto, tempo do agente e métricas de spec, gravado em `.ai-metrics/reports/`.

**Independent Test**: com eventos sintéticos de uma feature (sem depender de US3–US6), `report <feature>` gera o Markdown com todos os campos exigidos, `n` visível, `unknown`/`n/a` no lugar de `0`, e recusa gravar se `.ai-metrics/` não estiver ignorado (quickstart §4, parte do §8).

### Tests for User Story 2 ⚠️ (escrever primeiro; devem falhar)

- [X] T025 [P] [US2] Escrever `tools/ai_metrics/tests/test_metrics_phases.py`: escrita executável vs `ignore_paths` (`specs/**`, `.md`, `.specify/**`, `.claude/**`, fora do repo não contam), Pré-Implementação/Implementação/pós-first-pass sem dividir tokens dentro do turno, `firstProductionCodeWrite` à parte, `implementationStartedAt = unknown` sem escrita executável, submétricas (`specArtifact` > `grill` > `planning` > `other`, cada turno em um só rótulo) (FR-022…FR-026)
- [X] T026 [P] [US2] Escrever `tools/ai_metrics/tests/test_metrics_firstpass.py`: ciclo prompt→`end_turn`; ciclo de entrega estrutural (`speckit-implement` sem faixa de tarefas) vs `assumed`; `verified-green` vs `commit-proxy` vs `unknown`; `cyclesUntilFirstPass` e `firstPassSource`; `firstPass.corrected` sobrepõe; **nenhum** indicador binário; `postFirstPassTokens`/razão/churn/turnos humanos/arquivos reeditados; `fixCycles` com a regra de TDD do `data-model.md` (primeiro vermelho após teste escrito sem edição de produção não conta; depois conta) (FR-027…FR-030)
- [X] T027 [P] [US2] Escrever `tools/ai_metrics/tests/test_metrics_context_time.py`: `agentCycleSeconds` de `turn_duration` (fallback por timestamps marcado `estimated`), mediana do intervalo entre ciclos rotulada como contexto, `idle` ≥ 30 min fora da mediana, sem "tempo humano", contexto por chamada (`in+cacheRead+cacheCreate`) com pico/média, arquivos distintos lidos, `context.event` contados, tempo de API/ferramenta só por sessão (FR-032…FR-034)
- [X] T028 [P] [US2] Escrever `tools/ai_metrics/tests/test_metrics_spec.py` com repositório Git temporário: `Plan Path Coverage` (recall e precisão de `tasks.md` vs arquivos executáveis do diff), `Spec Changes After Implementation Start` (turnos e tokens), `n/a` (nunca `0`) sem `tasks.md`/spec (FR-031)
- [X] T029 [P] [US2] Escrever `tools/ai_metrics/tests/test_report.py`: ordem das seções, todos os campos de FR-041, `n` visível, aviso curto em cada métrica que pode enganar, normalizadas como secundárias, frases descritivas determinísticas **sem** linguagem causal, recusa gravar quando `.ai-metrics/` não está ignorado (FR-040b), grava só em `.ai-metrics/reports/<featureId>.md` e sobrescreve, recusa/avisa com `exit 2` se `verify` falhar, guarda do nome do bot na escrita, desempenho < 10 s com ~500 turnos sintéticos (SC-006) (FR-040, FR-040a, FR-040b, FR-041, FR-042)

### Implementation for User Story 2

- [X] T030 [US2] Em `tools/ai_metrics/ingest.py`, emitir `feature.born` ao ver um `gitBranch` novo (≠ `main`/`master`), com `bornAt` do reflog (`gitinfo.branch_created_at`) ou do primeiro turno (`bornSource`), `dataClass: observed`, `coverage: complete` (a regra de `partial` fica na US4)
- [X] T031 [US2] Implementar em `tools/ai_metrics/model.py` o carregamento do histórico em estruturas (turnos, prompts, ciclos, sessões, features) e a atribuição **mínima** por branch (`gitBranch == featureId`); ciclos = `prompt` → turnos da sessão até o próximo `prompt`
- [X] T032 [US2] Implementar em `tools/ai_metrics/metrics.py` as fases e as submétricas de Pré-Implementação, detectando escrita executável por `executable_paths`/`ignore_paths`/`production_paths` da config (faz T025 passar)
- [X] T033 [US2] Em `tools/ai_metrics/metrics.py`, implementar first-pass (`verified-green`, `commit-proxy`, `assumed`, `unknown`, `firstPass.corrected`), `fixCycles` com a regra de TDD e as métricas pós-first-pass (faz T026 passar)
- [X] T034 [US2] Em `tools/ai_metrics/metrics.py`, implementar contexto, tempo do agente, intervalo entre ciclos (mediana, `idle`) e workflow por skills (`direct`/`grill`/`speckit`/`grill+speckit` via `skill_labels`) (faz T027 passar)
- [X] T035 [US2] Em `tools/ai_metrics/metrics.py`, implementar `Plan Path Coverage` e `Spec Changes After Implementation Start` usando `gitinfo` (`n/a` sem spec) (faz T028 passar)
- [X] T036 [US2] Implementar em `tools/ai_metrics/report.py` a renderização do relatório Markdown (Fatos → Métricas → Análise → Evidências → Limitações; frases descritivas determinísticas; avisos; `n`; secundárias) e a gravação em `.ai-metrics/reports/<featureId>.md` com guarda de `git check-ignore`, `verify` prévio e guarda do nome do bot (faz T029 passar)
- [X] T037 [US2] Registrar em `tools/ai_metrics/cli.py` os subcomandos `report <featureId|alias> [--stdout] [--no-write]` e `report --all` (sem comparação ainda) e `timeline` (features em ordem cronológica com situação, `dataClass`, `coverage`, workflow)

**Checkpoint**: US1 + US2 = MVP. O relatório de uma feature sai ponta a ponta (quickstart §4 com dados sintéticos).

---

## Phase 5: User Story 3 - Atribuir o consumo à feature certa (Priority: P2)

**Goal**: atribuição determinística e retroativa (explícita → branch → caminho → `unattributed`), aliases, rascunhos, classes de custo, situação e correções por evento.

**Independent Test**: criar um branch de feature, trabalhar sem declarar nada e ver o consumo sob o nome do branch; criar `specs/NNN-*` e ver o alias automático; corrigir uma atribuição sem alterar o histórico (quickstart §5–§6).

### Tests for User Story 3 ⚠️ (escrever primeiro; devem falhar)

- [X] T038 [P] [US3] Escrever `tools/ai_metrics/tests/test_model_attribution.py`: ordem explícita > branch > caminho > `unattributed`; modos `explicit`/`inferred`/`corrected`/`unattributed`; `attribution.corrected` substitui o efeito de um registro sem editá-lo (`verify` continua ok, SC-011); duas features simultâneas sem sobreposição; branch derivado de branch de feature (Spec Kit) ignorado no nascimento; numeração do branch ≠ diretório de spec gera alias `spec-created-on-active-branch`, e leitura de spec existente gera `path-evidence`
- [X] T039 [P] [US3] Escrever `tools/ai_metrics/tests/test_model_drafts_status.py`: rascunho por sessão em `main`, vínculo só com feature nascida em `[início, fim + folga]` (caso real: setup termina 18:36:12, branch nasce segundos depois), rascunho sem vínculo = `exploração sem entrega` (nunca descartado), classes de custo, situação entregue (ancestral de `main` ou merge citando o branch), abandonada (30 dias, nunca integrada), volta a em andamento com nova atividade, `status.corrected` vence, em andamento fora dos agregados por classe (FR-017, FR-018)

### Implementation for User Story 3

- [X] T040 [US3] Em `tools/ai_metrics/ingest.py`, emitir `feature.alias` (`spec-created-on-active-branch` quando `Write` cria `specs/NNN-*/spec.md` num branch de feature; `path-evidence` para leituras/edições) e aplicar a regra de branch derivado via `gitinfo.created_from` ao emitir `feature.born` (FR-013, FR-014)
- [X] T041 [US3] Em `tools/ai_metrics/model.py`, implementar a atribuição completa por turno (explícita/corrigida > branch/alias > caminho `specs/NNN-*` > `unattributed`), escopos `sessionId`/`from-to`/`turns`, `tag: setup` e exclusão de turnos `analysis-overhead` (FR-015, FR-016, FR-021)
- [X] T042 [US3] Em `tools/ai_metrics/model.py`, implementar rascunhos com `draft_link_grace_minutes`, classes de custo e a situação da feature (entregue/abandonada/em andamento, `status.corrected`) usando `gitinfo` e a data do último turno (faz T038–T039 passarem)
- [X] T043 [US3] Em `tools/ai_metrics/metrics.py` e `tools/ai_metrics/report.py`, passar a usar a atribuição completa no relatório (modo de atribuição por trecho, `unattributed`, exploração sem entrega, situação da feature e classe de custo)
- [X] T044 [US3] Registrar em `tools/ai_metrics/cli.py` os subcomandos de correção que gravam eventos: `feature use`, `feature correct`, `feature status`, `feature first-pass`, `feature tag` (validam o featureId e passam pela guarda do nome do bot em `--reason`) (FR-019)

**Checkpoint**: US3 funciona sozinha e o relatório da US2 agora atribui de verdade.

---

## Phase 6: User Story 4 - Ser honesto sobre o que não foi medido (Priority: P2)

**Goal**: lacunas de cobertura, limites inferiores (`≥`), `unknown` em vez de `0`, backfill de 005/006 como histórico parcial, elegibilidade para comparação e tag `setup`.

**Independent Test**: `backfill` cria 005 e 006 como `historical`/`partial`; os relatórios dizem "tokens medidos", Pré-Implementação `unknown`, e ambas ficam fora de agregados (quickstart §4, §6).

### Tests for User Story 4 ⚠️ (escrever primeiro; devem falhar)

- [X] T045 [P] [US4] Escrever `tools/ai_metrics/tests/test_coverage.py`: métrica que toca lacuna não recuperada sai com `≥`; lacuna `recovered: true` só aparece nas Limitações; `unknown` (nunca `0`) sem medição; "tokens medidos"/"mínimo observado" para feature parcial, nunca "total"; feature `observed/complete` só se nascida com a captura ativa e sem lacuna não recuperada sobreposta; `gap add` grava `coverage.gap` com fonte/intervalo/motivo (SC-007, FR-035, FR-036, FR-039)
- [X] T046 [P] [US4] Escrever `tools/ai_metrics/tests/test_backfill.py` com repositório e transcrições sintéticas: `backfill` cria `feature.born` `historical`/`partial` para 005 e 006, atribui turnos por evidência de caminho dentro da janela dos commits e o resto fica `unattributed`, grava `coverage.gap` `copilot`, Pré-Implementação `unknown`, é idempotente, e as duas ficam fora de agregados mas na linha do tempo; a conversa de configuração marcada `setup` fica fora das agregações (SC-008, FR-037, FR-038)

### Implementation for User Story 4

- [X] T047 [US4] Em `tools/ai_metrics/metrics.py`, propagar `lower_bound` (`≥`) a toda métrica cujo conjunto de turnos intersecta uma lacuna não recuperada (incluindo `unlogged-api-calls`), `unknown` para ausência de medição, e a regra de elegibilidade (`observed` + `complete` + entregue/abandonada) (faz T045 passar)
- [X] T048 [US4] Em `tools/ai_metrics/report.py`, exibir `≥`, "tokens medidos"/"mínimo observado" para features parciais, a seção **Limitações** (lacunas por fonte/intervalo/motivo, divergência do `cost-state`, limite honesto do hash encadeado) e a marca `historical`/`setup`
- [X] T049 [US4] Implementar o subcomando `gap add --source --from --to --reason [--feature]` em `tools/ai_metrics/cli.py`
- [X] T050 [US4] Implementar o subcomando `backfill` (em `tools/ai_metrics/cli.py`, lógica em `tools/ai_metrics/model.py`): usa `history_windows` da config, grava `feature.born` `historical`/`partial`, `coverage.gap` `copilot` e `attribution.set` por evidência de caminho na janela; idempotente (faz T046 passar)
- [X] T051 [US4] Executar `backfill` e a marcação `feature tag 007-ai-dev-metrics --session 3fdf02d8-a612-4f16-b822-3650bb29d14f --tag setup` sobre os dados **reais** do dono e conferir os relatórios de 005/006 (sem publicar nada; só `.ai-metrics/` e `~/.cade-metrics/`)

**Checkpoint**: nenhum dado parcial aparece como total; 005/006 entram só na linha do tempo e na análise de caso.

---

## Phase 7: User Story 5 - Comparar workflows sem se enganar (Priority: P3)

**Goal**: comparação entre `direct`, `grill`, `speckit` e `grill+speckit` com `n`, classes de custo separadas, vieses conhecidos e aviso de comparação fraca.

**Independent Test**: com ≥ 2 features elegíveis sintéticas em workflows diferentes, `compare` mostra números brutos, `n` por grupo, classes separadas, vieses, `unattributed` por workflow e exclui históricas/`setup`.

### Tests for User Story 5 ⚠️ (escrever primeiro; devem falhar)

- [X] T052 [P] [US5] Escrever `tools/ai_metrics/tests/test_compare.py`: classificação por skills efetivamente usadas, `n` por workflow, classes (entregue/abandonada/exploração/`unattributed`) separadas, proporção de `unattributed` por workflow e marcação de "comparação fraca" quando muito diferente, lista fixa de vieses (escolha do workflow, `n` pequeno, aprendizado, modelo/esforço), exclusão de `historical` e `setup`, ausência de linguagem causal (FR-042, FR-043)

### Implementation for User Story 5

- [X] T053 [US5] Implementar em `tools/ai_metrics/report.py` a comparação entre workflows (números brutos, `n`, classes separadas, `unattributed` por workflow, "comparação fraca", vieses) e o arquivo `.ai-metrics/reports/_comparacao.md` com as mesmas guardas de escrita (faz T052 passar)
- [X] T054 [US5] Registrar `compare [--stdout]` e integrar a comparação a `report --all` em `tools/ai_metrics/cli.py`

**Checkpoint**: a comparação existe e nunca mistura dados históricos ou parciais.

---

## Phase 8: User Story 6 - Receber uma análise interpretativa (Priority: P3)

**Goal**: análise por LLM sob demanda, só com fatos e métricas estruturados, validada por código, registrada por evento e isolada como sobrecarga de análise.

**Independent Test**: `analyze` com um `claude` **simulado** aceita uma resposta válida e rejeita respostas com "porque", ID inexistente, número divergente ou afirmação sem evidência; a transcrição da execução vira `analysis-overhead` (quickstart §7).

### Tests for User Story 6 ⚠️ (escrever primeiro; devem falhar)

- [X] T055 [P] [US6] Escrever `tools/ai_metrics/tests/test_analysis.py` com um executável `claude` falso (script Python em diretório temporário no `PATH`): entrada montada só com fatos/métricas/cobertura (sem texto de conversa, sem valor monetário, `inputHash` estável); saída válida aceita; rejeições por JSON inválido, `type` fora do conjunto, evidência inexistente, número divergente, linguagem causal (`causou`, `causa`, `reduziu`, `porque`, `por causa de`, `devido a`, `levou a`, `resultou em`), afirmação sem evidência, "consumiu … no total" em feature parcial, ausência da menção a custos de especificação em comparação histórica, `limitations` vazio; `analysis.generated` gravado (aceita ou rejeitada); reanálise gera evento novo sem apagar o anterior (SC-009, FR-044…FR-047, FR-049)
- [X] T056 [P] [US6] Escrever `tools/ai_metrics/tests/test_analysis_overhead.py`: transcrição cuja `cwd` é `~/.cade-metrics/analysis-cwd` é ingerida com `source: analysis-overhead`, nunca atribuída à feature analisada nem à ativa, e somada à parte no relatório como "Sobrecarga de análise" (SC-010, FR-048)

### Implementation for User Story 6

- [X] T057 [US6] **Spike do `claude -p` (R13)**: confirmar nesta versão as flags reais (`--output-format json`, desabilitar ferramentas, limite de turnos, modelo) rodando uma chamada trivial a partir de `~/.cade-metrics/analysis-cwd/`, e registrar o resultado em `specs/007-ai-dev-metrics/research.md` (seção R13); ajustar o contrato `contracts/analysis-io.md` se algo divergir
- [X] T058 [US6] Implementar em `tools/ai_metrics/analysis.py` a montagem da entrada estruturada (`metrics`, `facts`, `coverage` com IDs estáveis, `promptVersion`, `inputHash`) a partir de `metrics.py`/`model.py`, sem transcrições
- [X] T059 [US6] Em `tools/ai_metrics/analysis.py`, implementar a execução (`subprocess` do `claude -p` com `cwd` em `analysis-cwd/` fora do repositório, tempo-limite, erro claro se o `claude` faltar) e o validador de saída conforme `contracts/analysis-io.md` (faz T055 passar)
- [X] T060 [US6] Em `tools/ai_metrics/ingest.py`, varrer também `~/.claude/projects/<slug do analysis-cwd>/` classificando `source: analysis-overhead`; em `tools/ai_metrics/model.py` e `tools/ai_metrics/report.py`, nunca atribuir esses turnos e mostrar "Sobrecarga de análise" à parte (faz T056 passar)
- [X] T061 [US6] Registrar `analyze <featureId> [--model m]` em `tools/ai_metrics/cli.py`: grava `analysis.generated` (aceita ou rejeitada com `rejectReasons`), e só quando aceita (re)escreve a seção **Análise** do relatório a partir do evento aceito mais recente (via `tools/ai_metrics/report.py`)

**Checkpoint**: análise isolada, validada e auditável; o relatório nunca mostra análise rejeitada.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: documentação, CI, privacidade e validação final

- [X] T062 [P] Documentar a ferramenta no `README.md` (seção curta em português: para que serve, `setup` único, fluxo `git switch -c <feature>` → trabalhar, comandos, onde ficam histórico e relatórios, limites do estudo), usando o placeholder `NomeDoBot` se o bot for citado
- [X] T063 [P] Adicionar ao `Makefile` o alvo `metrics-test` (`python -m unittest discover -s tools/ai_metrics/tests -t .`) e à ajuda do `make help`
- [X] T064 [P] Adicionar ao `.github/workflows/ci.yml`, no job de testes existente, um passo que roda os testes da ferramenta, mantendo `manage.py test tests` inalterado
- [X] T065 Escrever `tools/ai_metrics/tests/test_privacy.py`: varredura do histórico e dos relatórios gerados a partir de fixtures completas — sem texto de prompt/resposta/arquivo/comando, sem valor monetário (`$`, `USD`, `totalCostUSD`) e sem o valor de `TELEGRAM_BOT_USERNAME` (definido no teste como `ExemploBot`) (SC-004)
- [X] T066 Rodar o roteiro completo de `specs/007-ai-dev-metrics/quickstart.md` (§0–§8) com os dados reais e registrar no fim do `quickstart.md` o resultado (divergências reais do `cost-state`, tempo do `report`), sem colar conteúdo de conversas
- [X] T067 Conferir `git status`/`git check-ignore`: nada de `.ai-metrics/` versionável (SC-012) e `tools/ai_metrics/` versionado normalmente; antes de qualquer commit, procurar **no diff em stage** o valor real de `TELEGRAM_BOT_USERNAME` (lido do `.env` em memória, sem digitá-lo em comando) conforme a regra do projeto
- [X] T068 Rodar `python manage.py test tests` para confirmar que a suíte de produção não foi afetada e que não descobre os testes da ferramenta

---

## Phase 10: Ajustes pós-análise (`/speckit-analyze`, itens C1–C4)

**Purpose**: fechar lacunas entre a spec e a implementação apontadas pela análise. Ordem aplicada: C3 → C4 → C1 → C2.

- [X] T069 [US1] Exibir tempo de API e de ferramenta **por sessão** no relatório, fora dos `M-*` e rotulado "sessão inteira, não só esta feature" (`tools/ai_metrics/metrics.py`, `tools/ai_metrics/report.py`, `tools/ai_metrics/tests/test_metrics_context_time.py`) (FR-032, C1)
- [X] T070 [US1] Reparar a cauda interrompida do histórico antes da verificação e antes da leitura da captura: só descarta uma última linha incompleta sem `
` que a âncora ainda não reconhece; edição ou remoção de registros reconhecidos continua sendo detectada (`tools/ai_metrics/wal.py`, `tools/ai_metrics/ingest.py`, `tools/ai_metrics/tests/test_wal.py`, `tools/ai_metrics/tests/test_hook.py`) (edge case "Interrupção no meio da captura", C3)
- [X] T071 [US1] Detectar linhas ilegíveis **no meio** da transcrição (a última linha incompleta é normal), avisar no resumo e registrar `coverage.gap` `unreadable-lines`, idempotente (`tools/ai_metrics/ingest.py`, `tools/ai_metrics/cli.py`, `specs/007-ai-dev-metrics/contracts/wal-events.md`, `tools/ai_metrics/tests/test_ingest_validation.py`) (edge case "Formato de origem mudou", C4)
- [X] T072 Atualizar o SC-001 e a assumption de validação com os dados reais, e alinhar os edge cases e o FR-032 (`specs/007-ai-dev-metrics/spec.md`) (C2)

---

## Phase 11: Fechamento (`/speckit-analyze` C5–C16 e verificação final)

**Purpose**: aplicar o restante do relatório de análise e deixar código e documentação consistentes. Sem tarefas abertas.

- [X] T073 `errors.log` com nível e contexto (`timestamp<TAB>NÍVEL<TAB>contexto<TAB>mensagem`), leitura compatível com o formato antigo, e só linhas `ERROR` viram lacuna `hook-failed` (`tools/ai_metrics/ingest.py`, `tools/ai_metrics/tests/test_hook.py`) (Princípio VII, C9)
- [X] T074 [P] Teste que garante que todos os imports de `tools/ai_metrics` são da biblioteca padrão ou do próprio pacote (`tools/ai_metrics/tests/test_stdlib_only.py`) (FR-050, C10)
- [X] T075 [P] Alinhar a spec: `transcript-missing` e subagentes (C5), elegibilidade sem lacunas não recuperadas além da sistemática (C6), folga de 30 min do rascunho (C7), SC-006 com 500 turnos (C12) e glossário (C13) (`specs/007-ai-dev-metrics/spec.md`)
- [X] T076 [P] Documentar o arquivo local das análises aceitas (C8), `PowerShell`/`MultiEdit`, `feature use` com id desconhecido, `verify` que descarta cauda interrompida, opções ocultas e formato do `errors.log` (C16) (`contracts/analysis-io.md`, `contracts/cli.md`, `data-model.md`, `plan.md`, `research.md`)
- [X] T077 [P] Corrigir nomes de funções nas tarefas (C15) e referenciar o SC-005 (C11); C14 (sobreposição entre FR-035/036 e FR-042/043) mantido de propósito: os pares tratam aspectos diferentes (marcação vs. apresentação) e cada um tem seu teste (`specs/007-ai-dev-metrics/tasks.md`)
- [X] T078 Fechar T024 (hook `Stop` verificado em sessão aberta: dispara, cwd = raiz do projeto, formato do stdin em `research.md` R4) e remover o dump do stdin, que continha texto de resposta
- [X] T079 Investigar a sessão `3a4857cb` (só `main`, toca `specs/002`, `003` e `004`, termina 18:57 UTC, antes da criação do branch 005 às 19:15 UTC): **não** há evidência de que seja da feature 005, então nenhuma atribuição foi criada
- [X] T080 Decidir `production_paths`: `tools/**` fica **fora** (é ferramenta de desenvolvimento que não vai para a imagem; segue como artefato executável, então conta para início da Implementação, churn e ciclos de correção). Regra de materialidade de divergência (≥ 1% dos tokens do modelo) mantida: nenhum requisito ou teste a contradiz

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências.
- **Foundational (Phase 2)**: depende do Setup; **bloqueia todas as user stories**.
- **US1 (Phase 3)** e **US2 (Phase 4)**: dependem da Foundational. US2 é testável com eventos sintéticos (não exige US1), mas o uso real precisa da US1.
- **US3 (Phase 5)**: depende da Foundational; estende `model.py`/`metrics.py`/`report.py` da US2 (a US2 precisa existir antes).
- **US4 (Phase 6)**: depende de US2; usa atribuição da US3 no `backfill` (T050 depende de T041).
- **US5 (Phase 7)**: depende de US3 (classes de custo) e US4 (elegibilidade, cobertura).
- **US6 (Phase 8)**: depende de US2 (métricas) e de US1 (`ingest`); a parte de sobrecarga usa a atribuição da US3.
- **Polish (Phase 9)**: depende das stories desejadas concluídas.

### Dependências dentro das stories

- Testes primeiro (devem falhar), depois a implementação.
- `ingest.py`: T016 → T017 → T018 → T019 → T020 → T021 (mesmo arquivo, sequencial); depois T022.
- `metrics.py`: T032 → T033 → T034 → T035 → T043 → T047 (mesmo arquivo, sequencial).
- `report.py`: T036 → T043 → T048 → T053 → T060/T061.
- `cli.py`: T011 → T022 → T023 → T037 → T044 → T049 → T050 → T054 → T061 (sequencial; um arquivo).
- T030 (feature.born) precede T040 (alias) no mesmo arquivo.

### Parallel Opportunities

- Setup: T002, T003, T004 em paralelo (após T001).
- Foundational: T005, T006, T009 em paralelo (arquivos de teste distintos); T007 → T008 → T010 → T011 em sequência.
- US1: T012–T015 em paralelo (4 arquivos de teste).
- US2: T025–T029 em paralelo (5 arquivos de teste).
- US3: T038, T039 em paralelo. US4: T045, T046 em paralelo. US6: T055, T056 em paralelo.
- Polish: T062, T063, T064 em paralelo.
- Depois da US2, US3 e a preparação de testes de US4/US5/US6 podem andar em paralelo por desenvolvedores diferentes (cuidado com os arquivos compartilhados listados acima).

---

## Parallel Example: User Story 1

```bash
# Testes da US1 juntos (arquivos distintos):
Task: "test_ingest.py em tools/ai_metrics/tests/test_ingest.py"
Task: "test_ingest_validation.py em tools/ai_metrics/tests/test_ingest_validation.py"
Task: "test_hook.py em tools/ai_metrics/tests/test_hook.py"
Task: "test_setup.py em tools/ai_metrics/tests/test_setup.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Phase 1 (Setup) e Phase 2 (Foundational).
2. Phase 3 (US1): captura, integridade, hook e `setup` → **validar** com quickstart §0–§3.
3. Phase 4 (US2): relatório por feature → **validar** com quickstart §4 (dados sintéticos).
4. Usar no dia a dia já com o MVP: `setup` uma vez, `git switch -c <feature>`, trabalhar.

### Incremental Delivery

1. MVP → depois US3 (atribuição correta) → US4 (honestidade e backfill) → US5 (comparação) → US6 (análise por LLM).
2. Cada story acrescenta valor sem quebrar a anterior; `verify` deve continuar `exit 0` após cada uma.
3. Ponto de atenção real: dados do dono começam a ser instrumentados só a partir do `setup`; quanto antes o MVP rodar, mais features entram como `observed/complete`.

---

## Notes

- [P] = arquivos diferentes, sem dependência.
- Verificar que os testes falham antes de implementar; commitar após cada tarefa ou grupo lógico (Conventional Commits).
- Fixtures **sintéticas** apenas: nunca copiar transcrições reais para o repositório.
- T024 e T057 eram spikes de itens não verificados da spec (hook `Stop` no Windows; flags do `claude -p`); ambos foram verificados e o resultado está em `research.md` (R4 e R13).
- Sem emenda à constituição prevista; se algum spike mudar isso, parar e usar `/speckit-constitution`.
