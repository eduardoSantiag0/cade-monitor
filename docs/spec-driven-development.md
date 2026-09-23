### 🧪 Exemplo real: `007-ai-dev-metrics`

A feature `007-ai-dev-metrics` começou com uma ideia relativamente simples: **acompanhar quantos tokens eu estava gastando ao desenvolver com IA** e tentar entender se usar SDD, Grill Me e GitHub Spec Kit realmente compensava o custo adicional.

### 🔍 Descoberta com Grill Me

Antes de escrever qualquer especificação, usei o `Grill Me` como uma etapa de descoberta. A intenção era pressionar a ideia antes de transformá-la em requisito formal.

Essa conversa acabou levantando várias perguntas que eu ainda não tinha considerado:

* 🧩 Como associar automaticamente cada interação a uma feature?
* 👀 Como evitar que o próprio sistema de métricas altere aquilo que está sendo medido?
* 📜 Onde e como armazenar um WAL append-only?
* 🔄 O que realmente conta como retrabalho?
* 🏁 Quando existe um primeiro resultado da implementação?
* 📊 Quais métricas são objetivas e quais apenas parecem objetivas?

Algumas ideias foram descartadas durante esse processo. 🗑️ Por exemplo, abandonei o `Useful Spec Ratio`, o custo em dólares e um `First-Pass Success` binário, porque essas métricas poderiam produzir interpretações enganosas ou uma falsa sensação de precisão.

### 🌱 Nascimento da feature

Depois que as principais decisões estavam maduras, criei a branch:

`007-ai-dev-metrics`

A criação da branch também passou a representar o nascimento formal da feature.

### 📝 Especificação

Em seguida, usei `/speckit.specify` para transformar toda aquela discussão em requisitos formais.

O objetivo já não era mais descobrir a solução, mas registrar de forma clara **o que a feature deveria fazer, seus limites e seus critérios de sucesso**.

### ❓ Esclarecimento

Depois veio o `/speckit.clarify`.

Nessa etapa, as ambiguidades restantes foram fechadas, como:

* quando uma feature deve ser considerada entregue ou abandonada;
* como evitar que TDD seja confundido com retrabalho;
* onde os relatórios locais devem ser armazenados;
* como tratar falhas de captura e concorrência;
* como lidar com dados históricos incompletos.

### 🏗️ Planejamento técnico

Com essas decisões fechadas, rodei `/speckit.plan`.

O plano verificou a constituição do projeto, pesquisou detalhes técnicos que eu havia deliberadamente deixado em aberto e produziu artefatos como:

* `plan.md`
* `research.md`
* `data-model.md`
* contratos
* `quickstart.md`

Isso foi importante porque eu não queria decidir detalhes técnicos prematuramente durante o Grill Me.

Algumas questões — como o funcionamento real do hook `Stop` do Claude Code no Windows e a estrutura dos transcripts — pertenciam ao **plano técnico**, não à especificação funcional.

### 🧱 Tarefas

Por fim, `/speckit.tasks` transforma esse plano em uma sequência concreta de trabalho.

Cada decisão grande vira tarefas menores, ordenadas e verificáveis, preparando o caminho para `/speckit.implement`.

### 🔄 Fluxo completo

O fluxo ficou, na prática:

`💡 Ideia → 🔥 Grill Me → 🌱 Branch → 📝 Specify → ❓ Clarify → 🏗️ Plan → 🧱 Tasks → 🔎 Analyze → 💻 Implement`

### 💡 O que mudou na minha forma de desenvolver

Esse exemplo representa bem como estou usando SDD neste projeto: **a especificação não é apenas documentação escrita antes do código**.

Ela registra um processo de descoberta no qual ideias são questionadas, decisões ruins são descartadas, ambiguidades são resolvidas, restrições do projeto são verificadas e só então a implementação começa.
