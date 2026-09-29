# Feature Specification: Pacote de autos (documentos públicos) do processo

**Feature Branch**: `012-autos-processo-pacote`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "Pacote ZIP dos documentos públicos de um processo monitorado (Autos)." Decisão já confirmada com o dono do projeto: a metade confidencial (pasta Confidencial/, documentos restritos via sessão autenticada do SEI) e um vigia de vínculo de documento restrito ficam inteiramente fora de escopo desta versão — exigiriam sessão autenticada/credencial de usuário no SEI, o que contraria o Princípio II atual da constituição.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Baixar o pacote completo de documentos públicos (Priority: P1)

Um usuário autenticado do painel, na página de um processo monitorado, pede a montagem de um ZIP
com todos os documentos públicos daquele processo. A montagem roda em segundo plano (nunca durante
o próprio pedido do usuário, já que processos grandes têm centenas de documentos), com uma pausa
entre cada download para não sobrecarregar o SEI. O usuário vê o andamento (na fila, processando,
pronto, ou falhou) e, quando pronto, baixa o ZIP por um link autenticado. Dentro do ZIP, os
documentos aparecem numerados na mesma ordem da Lista de Protocolos pública do processo.

**Why this priority**: É o valor central da feature — sem isso não há pacote algum. As Histórias 2
e 3 são regras de confiabilidade sobre esse mesmo fluxo, não funcionalidades separadas.

**Independent Test**: com um processo fixture com N documentos, todos com link público de
download, pedir a montagem e confirmar que o ZIP final tem N entradas na ordem correta, com nomes
numerados, disponível para download só depois de "pronto".

**Acceptance Scenarios**:

1. **Given** um processo com 5 documentos, todos com link público, **When** o usuário pede a
   montagem do pacote, **Then** o pedido é aceito imediatamente (sem o usuário esperar a montagem
   terminar) e o status inicial é "na fila" ou "processando".
2. **Given** um pedido de montagem em andamento, **When** o usuário consulta o status antes de
   terminar, **Then** vê "processando", sem conseguir baixar nada ainda.
3. **Given** a montagem terminou com sucesso, **When** o usuário acessa a página do processo,
   **Then** vê um link para baixar o ZIP, e o ZIP contém os 5 documentos nomeados "1. ...", "2.
   ...", ..., "5. ...", na mesma ordem da Lista de Protocolos.
4. **Given** um usuário não autenticado, **When** tenta acessar o link de download do pacote,
   **Then** o acesso é negado (mesma exigência de login já aplicada ao resto do painel).
5. **Given** já existe uma montagem em andamento (ou um pacote pronto recente) para um processo,
   **When** um segundo pedido chega para o mesmo processo, **Then** o sistema reaproveita o job
   existente em vez de iniciar uma montagem duplicada em paralelo.

---

### User Story 2 - Documento individual indisponível não derruba o pacote (Priority: P2)

Quando um documento específico da lista não tem link público de download — porque é restrito,
porque foi removido, ou por qualquer outro motivo que o próprio SEI já declara na página ou no
andamento do processo —, o pacote não falha por causa dele. Esse número na sequência vira um
arquivo de texto explicando o motivo (usando o texto que o próprio SEI/andamento já declara),
preservando a numeração original: nunca pula um número silenciosamente, nunca reordena os demais
documentos por causa de uma ausência.

**Why this priority**: Depende da História 1 já montando pacotes; é o que torna o pacote útil na
prática, já que praticamente todo processo real tem pelo menos um documento restrito/indisponível.

**Independent Test**: com um processo fixture de 5 documentos onde o 3º não tem link público mas o
andamento do processo já explica o motivo (ex.: "documento restrito"), confirmar que o pacote final
tem 5 entradas, a 3ª sendo um `.txt` com esse motivo, e as demais nos números corretos.

**Acceptance Scenarios**:

1. **Given** um documento sem link público, mas o andamento do processo já registra o motivo (ex.:
   "restrito", "documento removido"), **When** o pacote é montado, **Then** esse número vira um
   arquivo `.txt` com o motivo declarado, e a montagem continua normalmente para os demais.
2. **Given** um documento sem link público e SEM nenhuma indicação já extraída do processo
   explicando por quê, **When** o pacote é montado, **Then** esse caso NÃO vira um placeholder
   silencioso — ele soma para a checagem de integridade da História 3 (não é "aceitável" por
   suposição).
3. **Given** um pacote com 2 dos 5 documentos indisponíveis (motivo declarado para ambos), **When**
   o ZIP é entregue, **Then** as 5 posições existem (3 arquivos reais + 2 `.txt`), na ordem
   original, nenhum número pulado.

---

### User Story 3 - Integridade do pacote acima de completude forçada (Priority: P3)

Antes de entregar o ZIP como "pronto", o sistema confere que processou exatamente o número de
documentos que a própria página do processo declarou ter. Se bater (contando os placeholders da
História 2 como processados), o pacote fica pronto. Se não bater — sinal de que algo inesperado
aconteceu na extração, não coberto pela História 2 —, o pacote inteiro falha com uma mensagem
clara, em vez de ser entregue silenciosamente incompleto.

**Why this priority**: É a rede de segurança das duas histórias anteriores — menor prioridade
porque só entra em ação quando algo já deu errado, mas essencial para nunca entregar um pacote que
parece completo e não é.

**Independent Test**: com um processo fixture onde a contagem declarada de documentos é maior do
que o que a extração consegue encontrar (nem como documento real, nem como placeholder explicado),
confirmar que o job termina como "falhou", com uma mensagem legível, e nenhum ZIP fica disponível
para download.

**Acceptance Scenarios**:

1. **Given** a página do processo declara 5 documentos e a extração encontra os 5 (reais ou
   placeholders explicados), **When** a montagem termina, **Then** o pacote fica "pronto".
2. **Given** a página declara 5 documentos mas a extração só encontra 4 (o 5º não é nem baixável
   nem tem motivo declarado em lugar algum já extraído), **When** a montagem termina, **Then** o
   job fica "falhou", com uma mensagem indicando a divergência, e nenhum ZIP parcial é
   disponibilizado para download.
3. **Given** um job que falhou por integridade, **When** o usuário pede a montagem novamente (ex.:
   depois que o SEI foi corrigido ou o problema era transitório), **Then** um novo job é aceito
   normalmente (a falha anterior não bloqueia novas tentativas).

---

### Edge Cases

- Processo com centenas de documentos: a montagem continua funcionando (mais devagar, pela pausa
  entre downloads), sem estourar o tempo/memória do processo principal da aplicação — a montagem
  roda no worker de segundo plano, nunca no request do usuário.
- Falha de rede ao baixar UM documento específico (não a página do processo em si): esse documento
  específico é tratado como indisponível (mesma regra da História 2) só se houver um motivo já
  declarado; senão, conta para a checagem de integridade da História 3.
- Um documento entre os autos é, ele mesmo, um arquivo ZIP: entra no pacote como está (um arquivo
  ZIP dentro do ZIP), sem ser aberto/expandido nesta versão.
- Um documento só existe como página nativa do SEI, sem nenhum arquivo baixável (ex.: texto gerado
  na hora pelo próprio sistema do SEI, sem PDF anexado): tratado como "sem link público de
  download", seguindo a mesma regra da História 2 (placeholder se houver motivo declarado; conta
  para a integridade senão houver).
- Pacote pronto há muito tempo sem ninguém baixar: o arquivo eventualmente expira/é removido do
  disco (não fica acumulando indefinidamente); um novo pedido depois da expiração inicia uma nova
  montagem.
- Dois usuários diferentes pedem o pacote do mesmo processo quase ao mesmo tempo: ambos acabam
  vendo o mesmo job (o segundo pedido reaproveita o primeiro, História 1 cenário 5) — nenhum dos
  dois espera por uma montagem duplicada.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST permitir que um usuário autenticado peça a montagem de um pacote ZIP
  de documentos públicos para qualquer processo monitorado, a partir da página desse processo.
- **FR-002**: O sistema MUST processar a montagem em segundo plano (nunca de forma síncrona dentro
  do pedido HTTP do usuário) e MUST expor o andamento do job (na fila/processando/pronto/falhou)
  de forma que o usuário consiga consultar sem precisar esperar bloqueado.
- **FR-003**: O sistema MUST aplicar uma pausa configurável entre o download de cada documento
  dentro de um mesmo job, para não gerar rajada de requisições ao SEI.
- **FR-004**: O sistema MUST nomear/numerar cada entrada do ZIP (documento real ou placeholder) na
  mesma ordem em que aparece na Lista de Protocolos pública do processo, sem pular nem reordenar
  números.
- **FR-005**: O sistema MUST reaproveitar um job já em andamento (ou um pacote já pronto e ainda
  válido) para o mesmo processo, em vez de iniciar uma segunda montagem em paralelo, quando um
  novo pedido chega para esse processo.
- **FR-006**: O sistema MUST exigir autenticação para pedir a montagem e para baixar o pacote
  pronto, mesma exigência já aplicada ao resto do painel.
- **FR-007**: Quando um documento da lista não tiver link público de download, o sistema MUST
  verificar se já existe, nos dados já extraídos do processo (andamento ou página), uma indicação
  explicando o motivo da ausência; havendo indicação, MUST criar um arquivo de texto nessa posição
  com o motivo declarado, e MUST continuar a montagem dos demais documentos normalmente.
- **FR-008**: Quando um documento não tiver link público E não houver nenhuma indicação já extraída
  explicando o motivo, o sistema MUST NOT inventar um placeholder — esse caso MUST contar como uma
  divergência para a checagem de integridade (FR-009).
- **FR-009**: Antes de marcar um pacote como "pronto", o sistema MUST conferir que o número de
  entradas processadas (documentos reais + placeholders explicados) é exatamente igual ao número de
  documentos que a própria página do processo declara ter; havendo divergência, o sistema MUST
  marcar o job como "falhou" com uma mensagem legível, e MUST NOT disponibilizar nenhum ZIP parcial
  para download.
- **FR-010**: O sistema MUST permitir que o usuário peça uma nova montagem depois de um job que
  falhou, sem que a falha anterior bloqueie novas tentativas.
- **FR-011**: O sistema MUST expirar/remover pacotes prontos após um período configurável, sem
  acumular arquivos indefinidamente.
- **FR-012**: O sistema MUST NOT incluir, nesta versão, nenhum documento restrito que exija sessão
  autenticada no SEI — apenas documentos com link público de download entram no pacote como
  arquivo real.
- **FR-013**: O sistema MUST incluir um documento que seja, ele mesmo, um arquivo ZIP, como está
  (sem abrir/expandir seu conteúdo nesta versão).

### Key Entities *(include if feature involves data)*

- **Job de montagem de pacote**: por processo, o estado da montagem em andamento ou concluída
  (na fila/processando/pronto/falhou), quem pediu, quando, o caminho do arquivo pronto (quando
  aplicável), a mensagem de erro (quando falhou), e a validade/expiração do pacote pronto.
- **Entrada do pacote**: dentro de um job, cada posição numerada — documento real baixado, ou
  placeholder de texto com o motivo declarado da ausência.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Em teste automatizado com fixtures cobrindo documentos com link, documentos sem link
  com motivo declarado, e documentos que são eles mesmos um ZIP, o pacote final contém exatamente
  o número de entradas declarado pela página do processo, na ordem correta, em 100% dos cenários
  de fixture.
- **SC-002**: Falha de rede ao baixar um documento específico nunca derruba o job inteiro nem trava
  o processamento dos demais documentos (verificável simulando falha num documento do meio da
  lista e confirmando que os demais são processados).
- **SC-003**: Nenhum pacote é disponibilizado para download quando a contagem de documentos
  processados não bate com a contagem declarada pela página do processo (verificável pelo cenário
  de divergência forçada em teste).
- **SC-004**: Um segundo pedido de montagem para um processo que já tem job em andamento nunca
  resulta em dois jobs simultâneos para o mesmo processo (verificável por teste de concorrência/
  chamada dupla).

## Assumptions

- A metade confidencial (pasta "Confidencial/", documentos restritos via sessão autenticada do
  SEI) e um vigia de vínculo de documento restrito ficam inteiramente
  fora de escopo desta versão — decisão confirmada com o dono do projeto, por exigirem sessão
  autenticada/credencial de usuário no SEI, o que contraria o Princípio II atual da constituição.
  Retomar esse escopo no futuro exigiria uma emenda de constituição própria.
- Sem merge de PDFs, sem impressão de HTML-para-PDF (evita dependência nova de navegador
  headless). Um documento que só existe como página HTML nativa do SEI, sem arquivo baixável, é
  tratado como "sem link público" (segue a regra da História 2/FR-007).
- Sem extração recursiva de ZIPs aninhados dentro dos autos nesta versão — simplificação
  deliberada, evita o risco de zip-bomb/path-traversal que a expansão implicaria.
- O conteúdo binário dos documentos não é persistido em nenhum modelo/tabela nova — o SEI é a
  fonte de verdade sempre disponível, e o pacote pronto existe como arquivo (com expiração), não
  como dado armazenado permanentemente.
- A função de download de documento já existente no sistema (já usada por outras features) é
  reaproveitada para cada documento individual, incluindo qualquer limite de tamanho já
  configurado — sem reimplementar o download do zero.
