# Grill Me — métricas de desenvolvimento assistido por IA (insumo para `/speckit-specify`)

Consolidação da discussão de 2026-09-23. Nenhuma implementação foi feita. Feature sugerida: `007-ai-dev-metrics`.

## Objetivo

Ferramenta **local** que registra, de forma auditável, quantos tokens e quanto tempo o desenvolvimento assistido por IA consome por feature, para estudar (observacionalmente) se workflows mais estruturados (Grill Me, Spec Kit) compensam frente ao fluxo direto. Não é só um contador de tokens: inclui uma camada de análise interpretativa por LLM, separada dos fatos.

## Decisões

### Escopo e restrições
- Ferramenta local, **fora do app Django e do banco**. Só biblioteca padrão do Python.
- **Unidade: tokens.** Não existe valor em dólar em nenhum lugar (WAL, métricas, relatórios, entrada da LLM). O ingestor ignora o `totalCostUSD` do `cost-state`. A validação da ingestão compara tokens por modelo com o `modelUsage` da sessão.
- Total de tokens = entrada + saída + leitura de cache + criação de cache. Os quatro tipos ficam sempre gravados.
- Estudo **observacional e descritivo**. Sem afirmação causal, sem sorteio de workflow, números brutos como apresentação principal, `n` sempre visível, análise de caso enquanto `n` for pequeno.

### Identidade da feature
- `featureId` = **nome do branch criado no nascimento** (ex.: `git switch -c 007-ai-dev-metrics`). É a única ação manual obrigatória.
- O diretório `specs/NNN-*` criado pelo Spec Kit é tratado como **alias automático** (`feature.alias`, `source: spec-created-on-active-branch`). A numeração do branch e a do Spec Kit não precisam coincidir.
- Branch nunca é requisito de identidade, só a origem dela. Interações anteriores ao branch podem ser atribuídas retroativamente.
- Várias features podem estar em andamento ao mesmo tempo. `/feature <id> --workflow <w>` existe só como override/correção.
- Se um hook do Spec Kit (extensão git) criar outro branch a partir de um branch de feature, a regra de nascimento ignora esse branch.

### Atribuição
- Calculada **no relatório**, de forma determinística e retroativa. Nada de score de confiança.
- Ordem de prioridade: declaração explícita → evidência de caminho (`Edit`/`Write`/`Read` em `specs/NNN-*/`, criação de `spec.md`) → `unattributed`.
- Modos: `explicit`, `inferred`, `corrected`, `unattributed`. Correções são eventos novos (`attribution.corrected`), nunca edição.
- **Drafts:** conversas de descoberta geram um draft automático que só vincula a uma feature **criada na janela dele**. Drafts sem vínculo nunca são descartados e contam como `exploration_without_delivery`.
- Classes de custo distintas: feature entregue, feature abandonada, exploração sem entrega, `unattributed`. O relatório mostra a proporção de `unattributed` por workflow; se for muito diferente entre workflows, a comparação é marcada como fraca.
- Workflows detectados por skills usadas: `direct`, `grill`, `speckit`, `grill+speckit`. "Discussão de requisitos" e "SDD manual" não têm sinal observável.
- `gitBranch`, `sessionId` e `conversationId` são metadados e sinais auxiliares. Um `sessionId` por feature (modo de trabalho atual) é um sinal forte.

### WAL
- Arquivo `.jsonl` **fora do repositório** (ex.: `~/.cade-metrics/`). Backup por conta do usuário.
- Cada registro tem `seq` e hash do anterior (`prev`). Comando `verify` detecta edição ou remoção.
- Guarda **cópias dos valores** (tokens por tipo, timestamps, ferramenta e caminho tocado, modelo, effort, modo de permissão), com `sessionId`/`uuid` como referência de auditoria. **Nunca** guarda texto de prompt, respostas nem conteúdo de arquivos (regra do projeto sobre o nome do bot).
- Ingestor **idempotente**, deduplicando por `message.id`. O transcript grava uma linha por bloco de conteúdo, então a soma ingênua infla ~2,5×.
- Disparo: hook `Stop` do Claude Code + ingestão manual como reserva.
- Fatos e atribuição são camadas separadas. Eventos previstos: `attribution.set`, `attribution.corrected`, `feature.alias`, `firstPass.corrected`, `coverage.gap`, `analysis.generated`.

### Fases (neutras ao workflow)
- **Pré-Implementação:** nascimento → primeira escrita em **artefato executável** (código de produção, testes, migrations, scripts/config executáveis). Docs, ADRs, Markdown e `specs/**` ficam na pré-implementação. `firstProductionCodeWrite` é registrado à parte.
- **Implementação:** a partir do turno que contém a primeira escrita executável.
- **Pós-First-Pass:** ver abaixo.
- Submétricas dentro da Pré-Implementação: `Spec Artifact Cost` (turnos que escrevem em `specs/**`), Grill Cost, Planning Cost, outros. As skills servem só de **rótulo**, nunca como fronteira.
- Unidade de custo: a mensagem do assistente (turno). Um turno com a primeira escrita executável marca o início da implementação. Sem divisão artificial de tokens dentro do turno.
- "Artefato executável" e "verificação relevante" vêm de **configuração** (lista de caminhos, comandos de teste), não de inferência. Escritas fora do repositório e arquivos de ferramenta (`.specify/**`, `.claude/**`) não contam.

### firstPass e retrabalho
- **Ciclo** = prompt humano → trabalho do agente → `end_turn`.
- `firstPassAt` = fim do primeiro ciclo de **entrega** após `implementationStartedAt` cuja última verificação observada foi verde (`verified-green`) ou que contém um commit (`commit-proxy`). Senão `unknown`. Registrar também `firstPassSource` e `cyclesUntilFirstPass`.
- Entrega vs parcial: `speckit-implement` sem faixa de tarefas = `feature-delivery` estrutural; nos demais workflows o primeiro ciclo é `assumed`. Ciclo parcial deliberado é corrigido por evento (`firstPass.corrected`).
- **Sem First-Pass Success binário por enquanto.** Métricas principais, contínuas: `Post-First-Pass Cost` (tokens e razão), `Post-First-Pass Churn`, `Fix Cycles` (verificação falhou → edição), `Human Turns After First Pass`, arquivos previamente modificados alterados de novo. A causa (defect-fix, requirement-change, scope-extension, polish, unknown) é camada interpretativa fora do WAL.
- Se algum dia houver classificação binária, os limites são fixados **antes** de aplicá-la a dados novos.

### Spec (Useful Spec Ratio foi aposentado)
- **Plan Path Coverage** (só Spec Kit): recall e precisão dos caminhos do `tasks.md` contra os arquivos executáveis alterados (git).
- **Spec Changes After Implementation Start:** turnos e tokens que escrevem em `specs/**` depois do início da implementação. Ressalva: a regra "documentos acompanham o código" torna isso política, não defeito.
- Sem convenção de citar `FR-NNN` nos testes (mudaria o comportamento medido). Mapeamento requisito → código fica como camada interpretativa futura.
- Em features sem spec, essas métricas são "não se aplica", nunca `0`.

### Tempo
- Só **tempo do agente** (`agentCycleSeconds`: do prompt ao `end_turn`, inclui API e ferramentas). Modo automático de permissão, então a espera de aprovação é mínima. O modo de permissão é registrado como covariável.
- Sem "tempo humano". O intervalo entre ciclos é contexto rotulado ("inclui leitura, revisão e ausência"), mostrado por mediana, com `idle` a partir de 30 min.
- Tempo de API e de ferramenta existem só por sessão (`cost-state`).

### Contexto
- Pico e média do tamanho de contexto por chamada (entrada + leitura + criação de cache), número e volume de arquivos distintos lidos, e compactações/`/clear` como eventos de contexto.

### Campos mostrados junto de cada feature
Workflow, ordem cronológica, modelo, effort, modo de permissão, tokens por tipo e total, tokens por fase, ciclos até first-pass, fix cycles, turnos humanos pós-first-pass, churn, linhas executáveis adicionadas/removidas, arquivos executáveis alterados, contexto lido, componentes/apps afetados. Métricas normalizadas (ex.: tokens por linha) são secundárias.

### Cobertura de dados
- `coverage` é **por lacuna** (`coverage.gap`: fonte, intervalo, motivo — `copilot`, `hook-failed`, `transcript-missing`). Métrica que toca uma lacuna é marcada como **limite inferior** (`≥`). Ausência de medição é `unknown`, nunca `0`. Todo evento de custo registra sua `source`.
- **Backfill de 005 e 006 na v1**, como `dataClass: historical`, `coverage: partial`. Pré-implementação = `unknown` (spec rodou no Copilot). O total é descrito como "tokens medidos"/mínimo observado, nunca como total real. Ficam na timeline e na análise de caso, **fora das agregações entre workflows**.
- `observed/complete` = features instrumentadas desde o nascimento, elegíveis para comparações.

### Relatório por feature
`Facts` → `Metrics` (com frases descritivas determinísticas, sem "porque") → `Analysis` → `Evidence` → `Limitations`.

### Análise por LLM (na v1)
- Separada dos fatos. Recebe **somente fatos e métricas estruturados** (incluindo cobertura), nunca o transcript.
- Roda **sob demanda**, como subprocesso headless a partir de um diretório fora do repositório. O transcript dela é classificado como `analysis-overhead` pela origem, nunca atribuído à feature analisada nem à ativa.
- Saída em JSON: cada afirmação tipada como `fact`, `association`, `hypothesis` ou `unsupported`, com IDs de métricas como evidência e limitações. O código valida: IDs existem, números batem, linguagem causal ("causou", "reduziu", "porque", "por causa de") é rejeitada, afirmação sem evidência é rejeitada.
- Cada análise é um evento `analysis.generated` com modelo, versão do prompt e hash da entrada. Reanálise gera evento novo.
- Nunca deve dizer "consumiu X tokens no total" para feature parcial; nunca transformar correlação em causalidade. Comparações históricas mencionam a ausência de custos de especificação.

### Caso especial: esta conversa
A discussão de setup (sessão `3fdf02d8`) é atribuída retroativamente à primeira feature de métricas por evento manual, marcada como `setup`. Fica fora das agregações entre workflows.

## Métricas que podem enganar
1. **Total de tokens:** ~99% é leitura de cache, então mede contexto × número de chamadas.
2. **Fix cycles em TDD:** o teste vermelho esperado parece ciclo de correção. Tratar na spec.
3. **Post-First-Pass Cost Ratio:** depende do estilo de prompts e da regra do ciclo.
4. **Churn:** refatoração legítima e arquivos grandes o inflam.
5. **Pré-Implementação:** um Grill Me caro pode valer a pena, e o número sozinho não diz isso.
6. **Tokens por linha:** linha não é complexidade (migrações, boilerplate).
7. **Plan Path Coverage:** só Spec Kit; testes e arquivos não previstos derrubam a precisão sem ser erro.
8. **Edições de spec após a implementação:** política de documentação, não defeito.
9. **Comparação entre workflows:** viés de seleção (o workflow é escolhido pelo usuário), `n` pequeno, aprendizado ao longo do tempo, modelo/effort diferentes.

## Achados sobre os dados (Claude Code, verificados nos transcripts)
- Cada resposta traz `usage` com entrada, saída, `cache_read`, `cache_creation` e raciocínio, mais timestamp, modelo, effort e `gitBranch`.
- Uma linha por bloco de conteúdo repete o mesmo `usage` (na sessão da 006: 492 linhas, 195 chamadas únicas). Deduplicar por `message.id`.
- Transcripts não têm invocações `/speckit.*` das features 005/006: a spec rodou no Copilot. Desde o `specify init --integration claude`, as skills `speckit-*` aparecem nos transcripts.
- O script `create-new-feature.ps1` numera pelos diretórios em `specs/` e não cria branch.
- Na spec 006, só 3 dos 18 FR aparecem em código/testes (rastreabilidade por ID mediria hábito, não utilidade).

## Em aberto para a spec e o plano
- Nome final da feature (sugestão `007-ai-dev-metrics`) e onde o código mora no repositório (`scripts/`, `tools/` ou outra pasta).
- Configurações: caminhos executáveis, comandos de verificação (`pytest`, `manage.py test`), limite de `idle` (30 min).
- **Não verificado:** se o Claude Code apaga transcripts antigos (por isso o hook), se há transcripts de subagentes fora dos arquivos lidos, e o formato da entrada de um hook `Stop` no Windows.
- Tratamento de TDD nos ciclos de correção.
- Regra de atribuição do backfill de 005/006 (evidência de caminho, commits `6d098f9` e `95dbc2a`, trechos em `main`).
- **Constitution Check:** parece não exigir emenda (fora do app, sem novo banco, canal ou dependência de runtime), mas só o início da constituição foi lido; conferir princípios I (simplicidade/dependências), V (WAL só com metadados) e VIII (justificar o hash encadeado).

## Próximo passo
`git switch -c 007-ai-dev-metrics` → `/speckit-specify` com este documento como insumo.
