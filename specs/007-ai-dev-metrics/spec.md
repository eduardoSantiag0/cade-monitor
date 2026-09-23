# Feature Specification: Métricas de desenvolvimento assistido por IA

**Feature Branch**: `007-ai-dev-metrics`

**Created**: 2026-09-23

**Status**: Draft

**Input**: User description: "Ferramenta local que registra, de forma auditável, quantos tokens e quanto tempo o desenvolvimento assistido por IA consome por feature, para estudar de forma observacional se workflows mais estruturados (Grill Me, Spec Kit) compensam frente ao fluxo direto. Inclui uma camada de análise interpretativa por LLM, separada dos fatos. Insumo completo: `grill-ai-dev-metrics.md` (consolidação da discussão de 2026-09-23)."

## Contexto e princípios do estudo

Esta feature é uma **ferramenta de estudo do próprio desenvolvimento**, não uma funcionalidade
do CADE Monitor. Ela vive fora do app Django e do banco de dados, e não altera o comportamento
do produto.

O estudo é **observacional e descritivo**. Isso vale para tudo o que a ferramenta produz:

- Números brutos são a apresentação principal; o tamanho da amostra (`n`) é sempre visível.
- Nenhuma afirmação causal é feita ("X reduziu Y", "por causa de"). Só fatos, associações e
  hipóteses rotuladas como tal.
- A unidade de custo é **token**. Não existe valor monetário em nenhum lugar.
- Ausência de medição é `unknown`, nunca `0`.
- Enquanto `n` for pequeno, a análise de caso (uma feature por vez) vale mais que agregados.

## Clarifications

### Session 2026-09-23

- Q: Qual é a identidade de uma feature? → A: O nome do branch criado no nascimento da feature
  (ex.: `007-ai-dev-metrics`). É a única ação manual obrigatória. O diretório `specs/NNN-*` do
  Spec Kit é tratado como alias automático; as numerações não precisam coincidir.
- Q: Existe valor em dólar nas métricas? → A: Não. O custo estimado em dólar que o Claude Code
  informa é ignorado. A validação usa tokens por modelo.
- Q: Existe um "First-Pass Success" binário? → A: Não por enquanto. Só métricas contínuas de
  custo e retrabalho depois do primeiro ciclo de entrega.
- Q: A análise por LLM entra na v1? → A: Sim, sob demanda, separada dos fatos e restrita a fatos
  e métricas estruturados.
- Q: O histórico das features 005 e 006 entra? → A: Sim, como dado histórico parcial, fora das
  comparações entre workflows.
- Q: Quando uma feature é "entregue" ou "abandonada"? → A: Entregue = o branch da feature foi
  integrado ao branch principal. Abandonada = branch sem atividade por um período configurável
  (padrão 30 dias) e nunca integrado. Ambas são calculadas no relatório e corrigíveis por
  evento; o resto é "em andamento".
- Q: Como tratar TDD nos ciclos de correção? → A: Não conta como correção a primeira verificação
  vermelha que vem logo depois de um teste ser escrito ou alterado no mesmo ciclo, sem edição de
  código de produção antes dela. Depois disso, toda verificação que falha seguida de edição
  conta como ciclo de correção.
- Q: Como atribuir o histórico das features 005 e 006? → A: Pela mesma regra geral de evidência
  de caminho (`specs/005-*`, `specs/006-*`), com a janela de cada feature limitada pelos commits
  que a criaram e concluíram (`6d098f9` e `95dbc2a`). Turnos sem evidência ficam `unattributed`.
- Q: Como e onde o relatório é entregue? → A: Como Markdown em `.ai-metrics/reports/` dentro do
  diretório do projeto (ex.: `.ai-metrics/reports/007-ai-dev-metrics.md`), que é o artefato
  persistente principal, podendo também ser exibido no terminal. Todo o `.ai-metrics/` é
  ignorado pelo Git: são dados locais de estudo, nunca versionados nem publicados. O histórico
  de eventos continua fora do repositório.
- Q: O que acontece quando a captura automática falha ou roda em paralelo? → A: A captura nunca
  bloqueia nem falha o turno do assistente: em caso de erro, termina em silêncio, a lacuna
  (`hook-failed`) é registrada na próxima captura e o erro vai para um log local. Capturas
  simultâneas são serializadas, sem corromper a sequência do histórico.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar o consumo de forma auditável (Priority: P1)

Como desenvolvedor que usa um assistente de IA, quero que o consumo de tokens e o tempo de cada
sessão de trabalho sejam registrados automaticamente num histórico que eu consiga auditar, sem
que eu precise anotar nada durante o trabalho.

**Why this priority**: Sem dados confiáveis e completos desde o nascimento da feature, nenhuma
métrica, relatório ou análise tem valor. Os dados de origem podem ser perdidos ou mudar de
forma; por isso o registro precisa ser próprio e durável.

**Independent Test**: Trabalhar numa sessão curta com o assistente, encerrar o turno e conferir
que o histórico ganhou registros com tokens por tipo, modelo, horários e caminhos tocados. Rodar
a verificação de integridade e ver que ela passa; editar manualmente uma linha do histórico e
ver que a verificação falha apontando a posição.

**Acceptance Scenarios**:

1. **Given** uma sessão de trabalho concluída, **When** a captura roda (automaticamente ao fim do
   turno ou manualmente), **Then** o histórico contém, por resposta do assistente, os quatro
   tipos de token (entrada, saída, leitura de cache, criação de cache), horário, modelo, nível
   de esforço, modo de permissão, ferramentas usadas e caminhos tocados.
2. **Given** uma sessão já capturada, **When** a captura roda de novo sobre os mesmos dados,
   **Then** nada é duplicado e os totais não mudam.
3. **Given** que a fonte de dados repete a mesma resposta em várias linhas (uma por bloco de
   conteúdo), **When** a captura roda, **Then** cada resposta é contada uma única vez e a
   divergência do total por modelo em relação ao que a própria ferramenta de IA informa para a
   sessão é exibida (FR-003).
4. **Given** um histórico íntegro, **When** uma linha é editada ou removida por fora da
   ferramenta, **Then** a verificação de integridade falha e indica a partir de qual registro a
   sequência está quebrada.
5. **Given** qualquer sessão capturada, **When** o histórico é inspecionado, **Then** ele não
   contém texto de prompts, respostas do assistente nem conteúdo de arquivos: só valores
   numéricos, horários, nomes de ferramentas, caminhos e identificadores de referência.
6. **Given** que a captura automática falhou ou não rodou, **When** o desenvolvedor executa a
   captura manual, **Then** as sessões pendentes são recuperadas e a lacuna, se houver, fica
   registrada.

---

### User Story 2 - Ver o relatório de uma feature (Priority: P1)

Como desenvolvedor, quero abrir o relatório de uma feature e ver quanto ela consumiu em tokens
e em tempo do agente, dividido por fase, e quanto retrabalho houve depois da primeira entrega,
para entender o custo do meu fluxo naquela feature.

**Why this priority**: É o resultado tangível da ferramenta e a base do estudo. Junto com a
captura, forma o MVP.

**Independent Test**: Para uma feature com dados completos, gerar o relatório e conferir as
seções na ordem Fatos → Métricas → Análise → Evidências → Limitações, com os campos exigidos,
frases descritivas sem "porque" e o `n` visível.

**Acceptance Scenarios**:

1. **Given** uma feature instrumentada desde o nascimento, **When** o relatório é gerado,
   **Then** ele mostra workflow, ordem cronológica, modelo, esforço, modo de permissão, tokens
   por tipo e total, tokens por fase, ciclos até o first-pass, ciclos de correção, turnos
   humanos após o first-pass, churn, linhas e arquivos executáveis alterados, contexto lido e
   componentes afetados.
2. **Given** uma feature, **When** o relatório divide o custo em fases, **Then** a
   Pré-Implementação vai do nascimento até a primeira escrita em artefato executável, a
   Implementação começa no turno que contém essa escrita, e o custo depois do first-pass é
   mostrado à parte, sem dividir tokens dentro de um turno.
3. **Given** que a feature tem Spec Kit, **When** o relatório é gerado, **Then** ele mostra o
   custo de artefatos de especificação, o de Grill Me, o de planejamento e o restante dentro da
   Pré-Implementação, usando as skills só como rótulo, e mostra a cobertura dos caminhos
   planejados nas tarefas contra os arquivos executáveis realmente alterados (recall e
   precisão).
4. **Given** uma feature sem spec, **When** o relatório é gerado, **Then** as métricas de spec
   aparecem como "não se aplica", nunca como `0`.
5. **Given** que não há verificação verde nem commit depois do início da Implementação,
   **When** o relatório é gerado, **Then** o momento do first-pass é `unknown` e as métricas que
   dependem dele aparecem como `unknown`.
6. **Given** uma métrica que pode enganar (total de tokens, ciclos de correção, churn, tokens
   por linha etc.), **When** ela é exibida, **Then** vem acompanhada de aviso curto sobre a
   limitação, e métricas normalizadas aparecem como secundárias.
7. **Given** um relatório com tempo, **When** o tempo é exibido, **Then** só há tempo do agente
   por ciclo; o intervalo entre ciclos aparece rotulado como contexto ("inclui leitura, revisão
   e ausência"), por mediana, e intervalos de 30 minutos ou mais são marcados como ociosos.

---

### User Story 3 - Atribuir o consumo à feature certa (Priority: P2)

Como desenvolvedor que trabalha em várias features ao longo do tempo (e às vezes em paralelo),
quero que cada consumo seja atribuído à feature correta sem eu precisar declarar nada a cada
sessão, e poder corrigir atribuições erradas sem apagar o histórico.

**Why this priority**: Sem atribuição, o consumo fica solto e não há "por feature". Fica em P2
porque o relatório de US2 já entrega valor quando a atribuição é trivial (uma feature por vez),
mas a atribuição correta é o que torna os números comparáveis.

**Independent Test**: Criar um branch de feature, trabalhar nele sem declarar nada e gerar o
relatório: o consumo aparece sob o nome do branch. Depois, criar o diretório de spec da feature
e ver o alias registrado automaticamente.

**Acceptance Scenarios**:

1. **Given** um branch de feature recém-criado, **When** o trabalho acontece nele, **Then** o
   consumo é atribuído à feature identificada pelo nome do branch, sem nenhuma outra ação
   manual.
2. **Given** que o Spec Kit cria um diretório de spec com numeração diferente da do branch,
   **When** o diretório passa a existir na feature ativa, **Then** um alias automático liga os
   dois nomes, e o consumo continua numa única feature.
3. **Given** consumo anterior à existência do branch (conversa de descoberta), **When** uma
   feature é criada dentro da janela dessa conversa, **Then** o consumo é vinculado
   retroativamente a ela; **e** **Given** que nenhuma feature nasce nessa janela, **Then** o
   consumo permanece registrado como exploração sem entrega, nunca descartado.
4. **Given** um branch criado automaticamente por extensão do Spec Kit a partir de um branch de
   feature, **When** a feature é identificada, **Then** esse branch derivado não vira uma nova
   feature.
5. **Given** que a regra de atribuição errou, **When** o desenvolvedor declara ou corrige a
   feature e o workflow de um período, **Then** a correção é registrada como um novo evento e o
   relatório passa a refletir a correção, com a atribuição original preservada no histórico.
6. **Given** consumo sem nenhuma evidência utilizável, **When** o relatório é gerado, **Then**
   ele fica como `unattributed`, e o relatório mostra a proporção de `unattributed` por
   workflow.
7. **Given** duas features em andamento no mesmo período, **When** o relatório de cada uma é
   gerado, **Then** cada uma recebe só o consumo com evidência para ela, sem sobreposição.

---

### User Story 4 - Ser honesto sobre o que não foi medido (Priority: P2)

Como desenvolvedor, quero que qualquer número que dependa de dados incompletos seja marcado
como mínimo observado, e quero incluir o histórico das features 005 e 006 sem que ele distorça
as comparações.

**Why this priority**: A credibilidade do estudo depende de nunca apresentar dado parcial como
total. O histórico existente é parcial por natureza (parte do trabalho ocorreu em outra
ferramenta), então essa regra é exercitada desde o primeiro dia.

**Independent Test**: Importar o histórico das features 005 e 006 e gerar os relatórios: o
consumo aparece como "tokens medidos", a Pré-Implementação como `unknown`, e as duas features
ficam fora de qualquer agregado entre workflows.

**Acceptance Scenarios**:

1. **Given** um período sem dados de uma fonte (outra ferramenta de IA, falha da captura,
   transcrição ausente), **When** isso é conhecido, **Then** uma lacuna de cobertura é
   registrada com fonte, intervalo e motivo.
2. **Given** uma métrica cujo intervalo toca uma lacuna, **When** ela é exibida, **Then** aparece
   como limite inferior (`≥`) e nunca como total exato.
3. **Given** as features 005 e 006, **When** o histórico é importado, **Then** elas ficam
   marcadas como históricas e de cobertura parcial, com Pré-Implementação `unknown`, aparecem na
   linha do tempo e na análise de caso, e são excluídas de agregações entre workflows.
4. **Given** uma feature parcial, **When** o relatório fala do seu custo, **Then** usa "tokens
   medidos" ou "mínimo observado" e nunca "total consumido".
5. **Given** uma feature instrumentada desde o nascimento e sem lacunas, **When** ela é
   classificada, **Then** fica como observada e completa, elegível para comparações.
6. **Given** a conversa de configuração deste próprio estudo, **When** o desenvolvedor a
   atribui manualmente à primeira feature de métricas com a marca `setup`, **Then** ela fica
   fora das agregações entre workflows.

---

### User Story 5 - Comparar workflows sem se enganar (Priority: P3)

Como desenvolvedor, quero comparar o custo de features feitas com fluxo direto, Grill Me, Spec
Kit e Grill Me + Spec Kit, vendo claramente as limitações da comparação, para decidir com
cautela quando vale a pena estruturar mais.

**Why this priority**: É o objetivo final do estudo, mas só faz sentido com várias features
instrumentadas. Até lá, o relatório por feature (US2) já serve como análise de caso.

**Independent Test**: Com pelo menos duas features elegíveis em workflows diferentes, gerar a
comparação e conferir que ela mostra números brutos, `n` por grupo, classes de custo separadas
e os avisos de limitação.

**Acceptance Scenarios**:

1. **Given** features elegíveis, **When** a comparação é gerada, **Then** cada feature é
   classificada num workflow (direto, Grill Me, Spec Kit, Grill Me + Spec Kit) a partir das
   skills efetivamente usadas.
2. **Given** a comparação, **When** ela é exibida, **Then** mostra `n` por workflow, separa
   feature entregue, feature abandonada, exploração sem entrega e `unattributed`, e lista os
   vieses conhecidos (o workflow é escolhido pelo desenvolvedor, `n` pequeno, aprendizado ao
   longo do tempo, modelo e esforço diferentes).
3. **Given** proporções de `unattributed` muito diferentes entre workflows, **When** a
   comparação é gerada, **Then** ela é marcada como fraca.
4. **Given** features históricas ou de setup, **When** a comparação é gerada, **Then** elas não
   entram nos agregados.

---

### User Story 6 - Receber uma análise interpretativa do relatório (Priority: P3)

Como desenvolvedor, quero pedir, sob demanda, uma interpretação em linguagem natural dos
fatos e métricas de uma feature, com cada afirmação classificada e amarrada a evidências, para
levantar hipóteses sem confundir interpretação com fato.

**Why this priority**: Agrega leitura e hipóteses, mas nenhum dado novo. Só é útil depois que
fatos e métricas existem e são confiáveis.

**Independent Test**: Pedir a análise de uma feature e conferir que cada afirmação tem tipo e
evidência, que linguagem causal é rejeitada e que o consumo da própria análise não aparece
atribuído a nenhuma feature.

**Acceptance Scenarios**:

1. **Given** uma feature com relatório, **When** a análise é pedida, **Then** a entrada da
   análise contém somente fatos e métricas estruturados (incluindo cobertura), nunca o conteúdo
   das conversas.
2. **Given** a resposta da análise, **When** ela é validada, **Then** cada afirmação tem um tipo
   (fato, associação, hipótese ou sem suporte), referencia métricas que existem, e os números
   citados conferem com os dados.
3. **Given** uma resposta com linguagem causal ("causou", "reduziu", "porque", "por causa de")
   ou afirmação sem evidência, **When** ela é validada, **Then** a resposta é rejeitada e não é
   apresentada como análise.
4. **Given** uma feature parcial, **When** a análise é gerada, **Then** ela não afirma "consumiu
   X tokens no total" e, em comparações com histórico, menciona a ausência de custos de
   especificação.
5. **Given** que a análise foi gerada, **When** o histórico é consultado, **Then** existe um
   evento com modelo, versão do roteiro da análise e identificador da entrada; uma nova análise
   gera um novo evento sem apagar o anterior.
6. **Given** o consumo da execução da própria análise, **When** a captura o encontra, **Then** é
   classificado como sobrecarga de análise e nunca é atribuído à feature analisada nem à ativa.

---

### Edge Cases

- **Falha ou concorrência na captura**: ver FR-010a e FR-010b; a falha nunca interrompe o
  trabalho do desenvolvedor e vira lacuna.
- **Interrupção no meio da captura**: uma queda durante a gravação pode deixar uma meia linha no
  fim do histórico; ela nunca foi reconhecida pela âncora, então é descartada na verificação
  seguinte e rodar a captura de novo completa o que faltou sem duplicar. Edição ou remoção de
  registros já reconhecidos continua sendo detectada.
- **Fonte de dados apagada ou rotacionada**: se a transcrição de origem sumir antes de ser
  capturada, o período vira lacuna `transcript-missing`, nunca `0`.
- **Sessões paralelas ou de subagentes**: consumo de subagentes e de sessões simultâneas não é
  contado duas vezes nem perdido; se a fonte deles não for localizada, vira lacuna.
- **Turno com várias escritas**: o turno que contém a primeira escrita executável inicia a
  Implementação inteiro; não há divisão de tokens dentro do turno.
- **Escritas que não contam**: escrever fora do repositório ou em arquivos de ferramenta
  (configuração do assistente e do Spec Kit) não marca início da Implementação.
- **TDD**: só a primeira verificação vermelha logo após escrever ou alterar um teste (sem
  código de produção editado antes) é excluída dos ciclos de correção (FR-030). Falhas
  seguintes contam, então a métrica ainda pode superestimar em ciclos TDD longos, e o aviso
  sobre isso permanece.
- **Ciclo parcial deliberado**: quando o primeiro ciclo de entrega foi na verdade parcial, o
  desenvolvedor corrige o first-pass por evento, sem editar dados.
- **Sem verificação e sem commit**: first-pass `unknown`; nenhuma métrica pós-first-pass é
  inventada.
- **Feature abandonada**: consumo entra na classe "feature abandonada", com `n` e custo próprios.
  Se o branch voltar a ter atividade depois de classificado como abandonado, a feature volta a
  "em andamento" no relatório seguinte.
- **Histórico adulterado**: a verificação de integridade falha de forma explícita, e nenhum
  relatório é gerado silenciosamente sobre dados suspeitos (avisa antes).
- **Formato de origem mudou**: campos ausentes ficam `unknown`. Linhas ilegíveis no meio de uma
  transcrição geram aviso e uma lacuna `unreadable-lines`, e nunca valores inventados. Uma última
  linha incompleta é normal (o arquivo pode estar sendo escrito) e não gera nada.
- **Ociosidade**: intervalos entre ciclos de 30 minutos ou mais são marcados como ociosos e não
  entram como trabalho.
- **Nome do bot do Telegram**: nenhum registro, relatório ou análise pode conter o nome ou
  @username real do bot do projeto.

## Requirements *(mandatory)*

### Functional Requirements

**Captura e histórico**

- **FR-001**: O sistema MUST capturar, por resposta do assistente, os quatro tipos de token
  (entrada, saída, leitura de cache, criação de cache), horário, modelo, nível de esforço, modo
  de permissão, ferramentas usadas e caminhos tocados, mais identificadores de sessão e de
  mensagem apenas como referência de auditoria.
- **FR-002**: O sistema MUST contar cada resposta do assistente uma única vez, mesmo que a fonte
  a repita em várias linhas, e a captura MUST ser idempotente (repetir não altera totais).
- **FR-003**: O sistema MUST comparar, por sessão, os tokens por modelo e por tipo capturados
  com os totais por modelo que a ferramenta de IA informa, e MUST exibir a divergência (absoluta
  e percentual). Divergência acima de um limite configurável (padrão 5% por tipo, no modelo
  principal) MUST ser sinalizada. A diferença observada MUST ser registrada como lacuna de
  cobertura (chamadas que a ferramenta contabiliza mas não grava na transcrição, como as de
  modelos auxiliares), e os totais capturados MUST ser tratados como limite inferior.
- **FR-004**: O sistema MUST ignorar qualquer valor monetário informado pela fonte; nenhum valor
  em dinheiro pode aparecer no histórico, nas métricas, nos relatórios ou na entrada da análise.
- **FR-005**: O sistema MUST manter um histórico de eventos de escrita apenas-anexar, guardado
  **fora do repositório**, onde cada registro tem número de sequência e vínculo criptográfico com
  o registro anterior.
- **FR-006**: O sistema MUST oferecer um comando de verificação que detecta edição ou remoção de
  registros e indica a primeira posição comprometida.
- **FR-007**: O sistema MUST NOT gravar texto de prompts, respostas do assistente ou conteúdo de
  arquivos no histórico.
- **FR-008**: O sistema MUST NOT gravar o nome ou @username real do bot do Telegram em nenhum
  registro, relatório, análise, mensagem ou documentação (Princípio V da constituição).
- **FR-009**: O sistema MUST manter fatos e atribuição em camadas separadas: atribuições e
  correções são eventos novos, nunca edição de fatos.
- **FR-010**: O sistema MUST disparar a captura automaticamente ao fim de cada turno do
  assistente e MUST oferecer captura manual como reserva.
- **FR-010a**: A captura automática MUST NOT bloquear nem fazer falhar o turno do assistente.
  Em caso de erro, MUST terminar sem interromper o trabalho, gravar o erro num log local e
  registrar a lacuna (`hook-failed`) na próxima captura bem-sucedida.
- **FR-010b**: Capturas simultâneas (ex.: duas sessões abertas) MUST ser serializadas, de modo
  que a sequência e o encadeamento do histórico nunca sejam corrompidos nem tenham registros
  duplicados.
- **FR-011**: O sistema MUST registrar, para todo evento de custo, a origem (`source`) dos dados.

**Identidade e atribuição**

- **FR-012**: O sistema MUST identificar uma feature pelo nome do branch criado no nascimento
  dela, sem exigir declaração adicional.
- **FR-013**: O sistema MUST registrar como alias automático (com origem) o diretório de spec
  criado pelo Spec Kit numa feature ativa, sem exigir que as numerações coincidam.
- **FR-014**: O sistema MUST ignorar, na regra de nascimento, branches criados por extensão do
  Spec Kit a partir de um branch de feature.
- **FR-015**: O sistema MUST calcular a atribuição no momento do relatório, de forma
  determinística e retroativa, na ordem: declaração explícita; o turno ter ocorrido no branch da
  feature (ou de um alias dela); evidência de caminho (leitura, edição ou criação em diretório de
  spec da feature); e por fim `unattributed`, sem nota de confiança.
- **FR-016**: O sistema MUST rotular a atribuição como `explicit`, `inferred`, `corrected` ou
  `unattributed`, e MUST permitir correções por eventos novos.
- **FR-017**: O sistema MUST tratar conversas de descoberta como rascunho automático, vinculado
  somente a uma feature criada na janela do próprio rascunho; rascunhos sem vínculo MUST ser
  mantidos e contados como exploração sem entrega.
- **FR-018**: O sistema MUST separar as classes de custo: feature entregue, feature abandonada,
  exploração sem entrega e `unattributed`. Uma feature MUST ser classificada, no momento do
  relatório, como **entregue** quando seu branch foi integrado ao branch principal, como
  **abandonada** quando ficou sem atividade por um período configurável (padrão 30 dias) sem ter
  sido integrada, e como **em andamento** nos demais casos. O desenvolvedor MUST poder corrigir
  a classificação por evento, e features em andamento MUST NOT entrar em agregados de custo por
  classe.
- **FR-019**: O sistema MUST permitir várias features em andamento ao mesmo tempo e MUST oferecer
  um comando para declarar ou corrigir manualmente feature e workflow.
- **FR-020**: O sistema MUST detectar o workflow pelas skills efetivamente usadas (`direct`,
  `grill`, `speckit`, `grill+speckit`) e MUST NOT inferir workflows sem sinal observável.
- **FR-021**: O sistema MUST usar branch, sessão e conversa apenas como metadados e sinais
  auxiliares, nunca como requisito de identidade.

**Fases, ciclos e métricas**

- **FR-022**: O sistema MUST usar o turno (mensagem do assistente) como unidade de custo, sem
  dividir tokens dentro de um turno.
- **FR-023**: O sistema MUST dividir cada feature em Pré-Implementação (do nascimento à primeira
  escrita em artefato executável), Implementação (a partir do turno dessa escrita) e
  pós-first-pass, neutras ao workflow.
- **FR-024**: "Artefato executável" e "verificação relevante" MUST vir de configuração editável
  (lista de caminhos e comandos de verificação), não de inferência. Escritas fora do repositório
  e em arquivos de ferramenta MUST NOT contar.
- **FR-025**: O sistema MUST registrar a primeira escrita em código de produção à parte do início
  da Implementação.
- **FR-026**: O sistema MUST detalhar a Pré-Implementação em custo de artefatos de spec, custo de
  Grill Me, custo de planejamento e outros, usando skills apenas como rótulo, nunca como
  fronteira de fase.
- **FR-027**: O sistema MUST definir ciclo como prompt humano → trabalho do agente → fim do
  turno, e calcular o momento do first-pass como o fim do primeiro ciclo de **entrega** após o
  início da Implementação cuja última verificação observada foi verde ou que contém um commit;
  caso contrário `unknown`. MUST registrar a origem do critério e o número de ciclos até o
  first-pass.
- **FR-028**: O sistema MUST tratar o primeiro ciclo como entrega quando o fluxo de implementação
  do Spec Kit roda sem faixa de tarefas, e como presumido nos demais workflows, e MUST permitir
  correção por evento.
- **FR-029**: O sistema MUST NOT expor um indicador binário de sucesso no first-pass. MUST expor
  métricas contínuas após o first-pass: tokens e razão de custo, churn, ciclos de correção, turnos
  humanos, e arquivos previamente modificados alterados novamente.
- **FR-030**: O sistema MUST contar um ciclo de correção sempre que uma verificação falha e é
  seguida de edição, exceto a **primeira** verificação vermelha que vem logo depois de um teste
  ser escrito ou alterado no mesmo ciclo, sem edição de código de produção antes dela (teste
  vermelho esperado em TDD). Falhas posteriores contam normalmente.
- **FR-031**: O sistema MUST calcular, só para features com Spec Kit, a cobertura dos caminhos
  planejados nas tarefas contra os arquivos executáveis alterados (recall e precisão), e o custo
  de escritas em specs após o início da Implementação; sem spec, "não se aplica".
- **FR-032**: O sistema MUST medir apenas tempo do agente por ciclo; MUST NOT reportar "tempo
  humano". O intervalo entre ciclos MUST aparecer rotulado como contexto, por mediana, com
  marcação de ociosidade a partir de um limite configurável (padrão 30 minutos). Tempo de API e
  de ferramenta MUST aparecer apenas por sessão, quando disponível, rotulado como "sessão inteira,
  não só esta feature" e sem virar métrica da feature.
- **FR-033**: O sistema MUST registrar como covariável o modo de permissão de cada sessão.
- **FR-034**: O sistema MUST medir contexto: pico e média do tamanho de contexto por chamada,
  número e volume de arquivos distintos lidos, e compactações ou limpezas de contexto como
  eventos.

**Cobertura e histórico**

- **FR-035**: O sistema MUST registrar lacunas de cobertura (fonte, intervalo, motivo) e MUST
  marcar como limite inferior (`≥`) toda métrica que toque uma lacuna.
- **FR-036**: O sistema MUST apresentar ausência de medição como `unknown`, nunca `0`, e MUST
  descrever custo parcial como "tokens medidos"/"mínimo observado".
- **FR-037**: O sistema MUST importar o histórico das features 005 e 006 como dado histórico de
  cobertura parcial, com Pré-Implementação `unknown`, e MUST excluí-las de agregações entre
  workflows, mantendo-as na linha do tempo e na análise de caso. A atribuição de turnos a cada
  uma MUST seguir a regra de evidência de caminho de FR-015 (leitura, edição ou criação em
  `specs/005-*` e `specs/006-*`), com a janela limitada aos commits que criaram e concluíram a
  feature; turnos sem evidência MUST ficar `unattributed`, sem atribuição presumida.
- **FR-038**: O sistema MUST permitir atribuir manualmente a conversa de configuração deste
  estudo à primeira feature de métricas, marcada como `setup`, fora das agregações.
- **FR-039**: O sistema MUST considerar elegíveis para comparação apenas features observadas e
  completas (instrumentadas desde o nascimento, sem lacunas).

**Relatório e comparação**

- **FR-040**: O relatório de feature MUST seguir a ordem Fatos → Métricas → Análise → Evidências →
  Limitações, com frases descritivas determinísticas nas métricas e sem linguagem causal.
- **FR-040a**: O relatório MUST ser gravado como arquivo Markdown em `.ai-metrics/reports/`, um
  por feature, nomeado pelo identificador da feature, e MAY também ser exibido no terminal.
  Gerar de novo MUST sobrescrever o arquivo da feature (o relatório é derivado do histórico).
- **FR-040b**: Todo o diretório `.ai-metrics/` MUST estar ignorado pelo Git. A ferramenta MUST
  verificar isso antes de gravar e, se o diretório não estiver ignorado, MUST recusar a gravação
  com mensagem clara em vez de arriscar a publicação dos dados. A ferramenta MUST NOT gravar
  nenhum arquivo de dados de consumo no repositório fora de `.ai-metrics/`.
- **FR-041**: O relatório MUST mostrar workflow, ordem cronológica, modelo, esforço, modo de
  permissão, tokens por tipo e total, tokens por fase, ciclos até o first-pass, ciclos de
  correção, turnos humanos pós-first-pass, churn, linhas e arquivos executáveis alterados,
  contexto lido e componentes afetados; métricas normalizadas MUST ser secundárias.
- **FR-042**: O relatório MUST mostrar `n` sempre que agregar, avisos curtos para métricas que
  podem enganar, e a proporção de `unattributed` por workflow, marcando comparações como fracas
  quando essa proporção divergir muito.
- **FR-043**: A comparação entre workflows MUST listar os vieses conhecidos e MUST NOT usar
  linguagem causal.

**Análise interpretativa**

- **FR-044**: O sistema MUST gerar a análise sob demanda, com entrada composta apenas de fatos e
  métricas estruturados (incluindo cobertura), nunca de transcrições.
- **FR-045**: A análise MUST ser produzida em formato estruturado, com cada afirmação tipada
  (fato, associação, hipótese, sem suporte), com identificadores de métricas como evidência e
  limitações.
- **FR-046**: O sistema MUST validar a análise e rejeitar: identificadores inexistentes, números
  que não conferem, linguagem causal e afirmações sem evidência.
- **FR-047**: O sistema MUST registrar cada análise como evento (modelo, versão do roteiro,
  identificador da entrada); reanálise MUST gerar novo evento.
- **FR-048**: A execução da análise MUST ocorrer isolada do repositório, e seu consumo MUST ser
  classificado como sobrecarga de análise por origem, nunca atribuído à feature analisada nem à
  ativa.
- **FR-049**: A análise MUST NOT afirmar custo total para feature parcial, transformar
  correlação em causalidade, e MUST mencionar a ausência de custos de especificação em
  comparações históricas.

**Restrições**

- **FR-050**: A ferramenta MUST rodar localmente, fora do app Django e do banco de dados, sem
  novas dependências de runtime além da biblioteca padrão da linguagem, e sem alterar o
  comportamento do CADE Monitor.

### Key Entities

- **Feature**: unidade de estudo. Identificada pelo nome do branch de nascimento; tem aliases,
  workflow, situação (em andamento, entregue, abandonada), classe de custo (entregue, abandonada,
  exploração, `unattributed`), classe de dado
  (observada ou histórica) e cobertura (completa ou parcial).
- **Alias**: nome alternativo da mesma feature (ex.: diretório de spec), com origem.
- **Registro do histórico**: evento imutável e encadeado (sequência, hash do anterior). Tipos:
  custo de resposta, atribuição, correção de atribuição, alias, correção de first-pass, lacuna de
  cobertura, análise gerada.
- **Turno**: uma resposta do assistente; unidade de custo (tokens por tipo, modelo, horário,
  ferramentas, caminhos).
- **Ciclo**: prompt humano até o fim do trabalho do agente; base de tempo do agente e do
  first-pass.
- **Fase**: Pré-Implementação, Implementação e pós-first-pass, com submétricas de
  Pré-Implementação.
- **Rascunho**: conversa de descoberta ainda sem feature; vinculado só a feature criada na sua
  janela; sem vínculo é exploração sem entrega.
- **Lacuna de cobertura**: fonte, intervalo e motivo pelos quais dados não foram medidos.
- **Análise**: interpretação gerada sob demanda, com afirmações tipadas, evidências e
  limitações, mais o evento que a registra.
- **Configuração**: caminhos executáveis, comandos de verificação e limite de ociosidade.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Em 100% das sessões capturadas, a divergência entre os totais capturados e os que
  a ferramenta de IA informa é exibida por modelo e por tipo; qualquer tipo material (≥ 1% dos
  tokens do modelo) acima de 5% é sinalizado no resumo da captura, e a diferença fica
  registrada como lacuna de cobertura.
- **SC-002**: Repetir a captura sobre dados já capturados resulta em zero registros novos e zero
  variação nos totais.
- **SC-003**: Editar ou remover qualquer registro do histórico é detectado em 100% dos casos
  testados, com indicação da primeira posição comprometida.
- **SC-004**: Uma varredura de todo o histórico e de todos os relatórios encontra zero trechos de
  prompt, de resposta, de conteúdo de arquivo, valores monetários e o nome real do bot.
- **SC-005**: Uma feature nova é rastreada de ponta a ponta com uma única ação manual (criar o
  branch), e o relatório dela sai sem nenhuma declaração adicional.
- **SC-006**: O relatório de uma feature com centenas de turnos é gerado em menos de 10
  segundos.
- **SC-007**: 100% das métricas que tocam uma lacuna aparecem como limite inferior ou `unknown`,
  e 0% aparecem como `0` quando não houve medição.
- **SC-008**: As features 005 e 006 aparecem na linha do tempo marcadas como históricas e
  parciais, e em 0% dos agregados entre workflows.
- **SC-009**: 100% das análises aceitas têm todas as afirmações com tipo e evidência
  verificável; 100% das respostas com linguagem causal ou evidência inexistente são rejeitadas.
- **SC-010**: O consumo da execução das análises aparece em 0% das features (fica só como
  sobrecarga de análise).
- **SC-011**: Uma correção de atribuição altera o relatório sem modificar nenhum registro
  anterior do histórico (a verificação de integridade continua passando).
- **SC-012**: Após gerar relatórios, o Git não vê nenhum arquivo novo para versionar (zero
  arquivos de consumo rastreáveis ou pendentes de commit), e a gravação é recusada se a regra de
  ignorar `.ai-metrics/` for removida.
- **SC-013**: Em 100% das falhas simuladas da captura automática, o turno do assistente termina
  normalmente, e a lacuna correspondente aparece no relatório seguinte; duas capturas
  simultâneas resultam em histórico íntegro e sem duplicatas.

## Assumptions

- O desenvolvedor usa o Claude Code como assistente principal; o uso de outras ferramentas
  (ex.: Copilot nas features 005 e 006) é tratado como lacuna, não capturado.
- Verificado nos dados reais (2026-09-23): as transcrições somam menos que os totais por modelo
  informados pela ferramenta, que inclui chamadas de modelos auxiliares sem registro na
  transcrição. A diferença no cache-read ficou entre 1,5% e 3,6% nas sessões de implementação,
  mas chegou a 19,7% (cache-read) e 8,2% (cache-creation) na conversa de Grill Me. Por isso a
  validação é uma divergência medida e sinalizada, não uma igualdade nem um valor esperado.
- Os dados de origem (transcrições) trazem, por resposta, tokens por tipo, horário, modelo,
  esforço e branch, como verificado nas conversas do projeto; a ferramenta tolera campos
  ausentes marcando-os como `unknown`.
- O local do histórico é uma pasta do usuário fora do repositório (ex.: sob o diretório pessoal);
  o backup é responsabilidade do usuário.
- O nome final da feature é `007-ai-dev-metrics`. O local do código dentro do repositório (ex.:
  `scripts/` ou `tools/`) fica para o plano, assim como os valores padrão de configuração
  (caminhos executáveis, comandos de verificação).
- Modo de permissão automático: a espera por aprovação humana é mínima, portanto o tempo do
  agente é uma boa aproximação do tempo de trabalho da máquina; o modo é registrado como
  covariável.
- Os commits `6d098f9` e `95dbc2a` delimitam as janelas de 005 e 006; se a janela exata de
  algum deles exigir ajuste (ex.: trechos já em `main`), isso é refinado no plano.
- Ainda não verificado, e tratado no plano: se a ferramenta de IA apaga transcrições antigas, se
  há transcrições de subagentes fora dos arquivos lidos, e o formato da entrada do disparo
  automático no Windows.
- Constitution Check preliminar: sem novo banco, canal de mensagens ou dependência de runtime,
  portanto sem emenda prevista. A conferência final dos Princípios I (simplicidade e
  dependências), V (histórico só com metadados) e VIII (justificar o vínculo criptográfico) fica
  no plano.
- Fora de escopo da v1: qualquer afirmação causal, sorteio de workflow, "tempo humano",
  mapeamento requisito → código (fica como camada interpretativa futura), classificação binária
  de first-pass e convenção de citar identificadores de requisitos nos testes.
