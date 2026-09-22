# Feature Specification: Bot do Telegram como canal principal

**Feature Branch**: `006-telegram-bot`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Implementar um bot do Telegram, que passa a ser a principal forma de comunicação com os usuários (o WhatsApp continua como opção). Fluxo: o usuário envia /start, o bot explica o que faz; com /watch <processo> o bot valida o número, consulta o processo pela primeira vez, salva o estado inicial e começa o monitoramento; o worker verifica periodicamente e, ao detectar mudança, envia alerta no Telegram. Comandos: /watch, /unwatch, /list, /status, /check (força uma consulta agora), /pause, /resume e /history (últimas movimentações). Decisões: webhook; acesso aberto com limite de processos por usuário; /check com cooldown para respeitar a cadência mínima de consulta ao SEI."

## Clarifications

### Session 2026-09-22

- Q: O bot funciona só em conversa privada ou também em grupos? → A: Privado **e** grupos. Um
  grupo funciona como um assinante próprio: os alertas chegam no grupo, e o limite de processos
  vale por grupo.
- Q: Quem pode comandar o bot num grupo? → A: (default definido no planejamento, sujeito a
  revisão do dono) Só administradores do grupo podem usar `/watch`, `/unwatch`, `/pause` e
  `/resume`. `/list`, `/status`, `/history` e `/check` ficam liberados para qualquer membro
  (`/check` já tem intervalo mínimo).
- Q: Assinantes já cadastrados pelo painel podem vincular o Telegram? → A: Não na v1. Cada chat
  do Telegram vira um assinante novo.
- Q: (pós-implementação) Como receber a última atualização com o documento? → A: Novo comando
  `/last_update <processo>`, que envia a última atualização e o PDF do protocolo mais recente. Os
  alertas no Telegram também passam a levar o arquivo do documento, e não só o link.
- Q: Limites padrão? → A: Mantidos: 10 processos por chat, intervalo mínimo de 5 min para
  `/check` e 5 movimentações no `/history`, todos configuráveis.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Começar a monitorar um processo pelo Telegram (Priority: P1)

Como pessoa interessada num processo do CADE, quero abrir o bot, entender o que ele faz e
mandar o número do processo para começar a acompanhá-lo, sem precisar de cadastro no painel
nem de alguém da equipe.

**Why this priority**: É a porta de entrada. Sem cadastro por autoatendimento, o Telegram não
substitui o fluxo atual (cadastro manual pelo painel) e nenhuma outra história tem usuário.

**Independent Test**: Num chat novo com o bot, enviar `/start` e depois
`/watch 08700.005905/2026-38`. O bot deve explicar o serviço, confirmar o recebimento e, em
seguida, avisar que o monitoramento começou, mostrando a última movimentação conhecida do
processo.

**Acceptance Scenarios**:

1. **Given** uma pessoa que nunca usou o bot, **When** ela envia `/start`, **Then** o bot se
   apresenta, explica em linguagem simples o que monitora e lista os comandos disponíveis.
2. **Given** um usuário do bot, **When** ele envia `/watch` com um número de processo em formato
   válido, **Then** o bot responde na hora que está consultando o processo e, em no máximo
   alguns minutos, confirma que o monitoramento começou, com a última movimentação conhecida.
3. **Given** um processo que outro usuário já monitora, **When** um novo usuário envia `/watch`
   com o mesmo número, **Then** o bot confirma o monitoramento imediatamente com o estado já
   conhecido, sem nova consulta ao site do CADE.
4. **Given** um número em formato inválido, **When** o usuário envia `/watch`, **Then** o bot
   explica o formato esperado com um exemplo e não cria nenhum monitoramento.
5. **Given** um número em formato válido que não existe no SEI, **When** a primeira consulta
   falha por processo inexistente, **Then** o bot avisa o usuário e o monitoramento não fica
   ativo para ele.
6. **Given** um usuário que já atingiu o limite de processos monitorados, **When** ele envia
   `/watch` para um novo processo, **Then** o bot recusa, informa o limite e sugere `/unwatch`.
7. **Given** um usuário que já monitora o processo, **When** ele envia `/watch` com o mesmo
   número, **Then** o bot informa que ele já acompanha esse processo e não duplica nada.

---

### User Story 2 - Receber alertas de movimentação no Telegram (Priority: P1)

Como usuário do bot, quero receber uma mensagem no Telegram assim que o sistema detectar uma
movimentação nova num processo que acompanho, para não precisar consultar o SEI manualmente.

**Why this priority**: É o valor central do produto. Sem alertas, o cadastro da História 1 não
serve para nada. As duas juntas formam o MVP.

**Independent Test**: Com um usuário monitorando um processo, simular uma mudança detectada pelo
worker e verificar que a mensagem chega no chat do usuário com o resumo da movimentação e o link
do processo.

**Acceptance Scenarios**:

1. **Given** um usuário monitorando um processo, **When** o worker detecta uma movimentação
   nova, **Then** o usuário recebe no Telegram uma mensagem em português com o processo, o
   resumo do que mudou e o link público.
2. **Given** vários usuários monitorando o mesmo processo, **When** uma mudança é detectada,
   **Then** todos recebem o alerta, e o site do CADE é consultado uma única vez por ciclo para
   aquele processo.
3. **Given** uma mudança com documentos novos, **When** o alerta é enviado, **Then** a mensagem
   lista os documentos com link, e os anexos são enviados quando disponíveis, no mesmo espírito
   do canal WhatsApp.
4. **Given** uma falha temporária de envio para o Telegram, **When** o envio falha, **Then** o
   sistema tenta de novo nos ciclos seguintes, até o limite de tentativas já usado pelos outros
   canais, e registra cada tentativa.
5. **Given** um usuário que bloqueou o bot, **When** um alerta é enviado, **Then** o sistema
   marca o usuário como inalcançável e para de tentar enviar para ele, sem afetar os demais.
6. **Given** assinantes que recebem por e-mail ou WhatsApp, **When** uma mudança é detectada,
   **Then** eles continuam recebendo pelos canais atuais, sem regressão.

---

### User Story 3 - Consultar e gerenciar meus processos (Priority: P2)

Como usuário do bot, quero ver quais processos acompanho, a situação de cada um e o histórico
recente, e poder parar de acompanhar um processo, para organizar meu acompanhamento sem ajuda.

**Why this priority**: Torna o autoatendimento completo e reduz pedidos à equipe, mas o MVP já
entrega valor sem esses comandos.

**Independent Test**: Com um usuário monitorando dois processos (um deles com mudanças
registradas), executar `/list`, `/status`, `/history` e `/unwatch` e conferir as respostas.

**Acceptance Scenarios**:

1. **Given** um usuário com processos monitorados, **When** ele envia `/list`, **Then** o bot
   lista cada processo com o rótulo, se está ativo ou pausado para ele e quando foi a última
   verificação.
2. **Given** um usuário sem processos, **When** ele envia `/list`, **Then** o bot explica como
   usar `/watch`.
3. **Given** um processo monitorado, **When** o usuário envia `/status <processo>`, **Then** o
   bot mostra a última movimentação conhecida, quando ela foi detectada e quando foi a última
   verificação.
4. **Given** um processo com mudanças registradas, **When** o usuário envia
   `/history <processo>`, **Then** o bot lista as últimas movimentações (até um limite
   configurável), da mais recente para a mais antiga, com data e resumo.
5. **Given** um processo monitorado, **When** o usuário envia `/unwatch <processo>`, **Then** o
   bot confirma, e o usuário deixa de receber alertas daquele processo. Se ninguém mais o
   acompanha, o processo deixa de ser consultado.
6. **Given** um processo que o usuário não acompanha, **When** ele usa `/status`, `/history`,
   `/check`, `/pause`, `/resume` ou `/unwatch` com esse número, **Then** o bot informa que ele
   não acompanha esse processo e não revela dados de monitoramentos de outras pessoas.

---

### User Story 4 - Pausar, retomar e forçar uma verificação (Priority: P3)

Como usuário do bot, quero pausar temporariamente os alertas de um processo, retomá-los depois
e pedir uma verificação imediata quando espero uma movimentação, respeitando os limites de
consulta ao site público.

**Why this priority**: Conveniência. O monitoramento periódico já cobre o essencial.

**Independent Test**: Pausar um processo e confirmar que o usuário não recebe o alerta de uma
mudança simulada. Retomar e confirmar que volta a receber. Enviar `/check` duas vezes seguidas
e confirmar que a segunda resposta usa o estado salvo e informa quando será possível verificar
de novo.

**Acceptance Scenarios**:

1. **Given** um processo monitorado, **When** o usuário envia `/pause <processo>`, **Then** ele
   para de receber alertas daquele processo. Os outros usuários do mesmo processo não são
   afetados.
2. **Given** um processo pausado pelo usuário, **When** ele envia `/resume <processo>`, **Then**
   volta a receber alertas a partir das próximas mudanças, sem receber as que ocorreram durante
   a pausa.
3. **Given** um processo cuja última verificação é mais antiga que o intervalo mínimo de
   verificação sob demanda, **When** o usuário envia `/check <processo>`, **Then** o bot avisa
   que vai verificar e, em no máximo alguns minutos, responde com "sem novidades" ou com o
   resumo da mudança.
4. **Given** um processo verificado há menos tempo que esse intervalo mínimo, **When** o
   usuário envia `/check`, **Then** o bot responde com o estado já salvo e informa em quanto
   tempo será possível pedir nova verificação, sem consultar o site do CADE.
5. **Given** uma mudança encontrada por um `/check`, **When** ela é registrada, **Then** os
   demais usuários do processo também recebem o alerta normal.

---

### User Story 5 - Acompanhar processos num grupo do Telegram (Priority: P3)

Como equipe que acompanha processos em conjunto, quero adicionar o bot a um grupo do Telegram
para que os alertas cheguem a todos os membros, com só os administradores decidindo quais
processos o grupo acompanha.

**Why this priority**: Amplia o alcance (uma mensagem para a equipe inteira), mas o uso
individual das histórias anteriores já cobre o essencial.

**Independent Test**: Adicionar o bot a um grupo de teste. Um administrador envia
`/watch <processo>`, um membro comum tenta `/unwatch` e é recusado, e uma mudança simulada gera
um único alerta no grupo.

**Acceptance Scenarios**:

1. **Given** o bot adicionado a um grupo, **When** alguém envia `/start` ou `/help` no grupo,
   **Then** o bot se apresenta e explica que os alertas do grupo chegam para todos os membros e
   que só administradores gerenciam os processos.
2. **Given** um administrador do grupo, **When** ele envia `/watch <processo>`, **Then** o
   processo passa a ser acompanhado pelo grupo, e as confirmações e alertas chegam no grupo.
3. **Given** um membro que não é administrador, **When** ele envia `/watch`, `/unwatch`,
   `/pause` ou `/resume` no grupo, **Then** o bot recusa e explica que só administradores podem
   fazer isso.
4. **Given** qualquer membro do grupo, **When** ele envia `/list`, `/status`, `/history` ou
   `/check`, **Then** o bot responde no grupo sobre os processos do grupo.
5. **Given** comandos no formato `/comando@NomeDoBot` (comum em grupos), **When** o bot os
   recebe, **Then** eles são tratados como o comando normal. Comandos dirigidos a outro bot são
   ignorados.
6. **Given** o bot removido do grupo, **When** houver alertas para aquele grupo, **Then** o
   grupo é marcado como inalcançável, como acontece com um usuário que bloqueou o bot.
7. **Given** um grupo que o Telegram converteu em supergrupo (troca de identificador), **When**
   o bot recebe o aviso de migração, **Then** os processos acompanhados continuam valendo para o
   novo identificador.

---

### Edge Cases

- O Telegram reenvia a mesma atualização (entrega duplicada): o comando é processado uma única
  vez.
- Chamadas ao endereço de recebimento sem a credencial secreta do Telegram: são recusadas sem
  processar nada.
- Mensagem sem comando ou comando desconhecido: o bot responde com a ajuda resumida.
- Número do processo com espaços, sem pontuação ou colado como link do SEI: o bot normaliza os
  formatos reconhecíveis para o formato canônico `NNNNN.NNNNNN/AAAA-DD`.
- O site do CADE está fora do ar durante a primeira leitura de um `/watch`: o bot avisa que não
  conseguiu consultar agora. O monitoramento continua agendado e o usuário é avisado quando a
  primeira leitura der certo.
- Mensagens muito longas (resumos de mudança grandes): são cortadas dentro do limite do
  Telegram, com o link do processo para ver o restante.
- O mesmo usuário acompanha um processo no privado e também pelo grupo: recebe o alerta nos dois
  lugares (são assinantes diferentes).
- Canais do Telegram (broadcast): fora do escopo. O bot ignora atualizações vindas de canais.
- Várias pessoas pedem `/check` do mesmo processo ao mesmo tempo: gera no máximo uma consulta ao
  site, e todas recebem a resposta.
- Usuário bloqueia o bot e depois o desbloqueia e envia `/start`: volta a ser alcançável, com os
  monitoramentos anteriores preservados.

## Requirements *(mandatory)*

### Functional Requirements

**Cadastro e acesso**

- **FR-001**: Qualquer pessoa MUST poder começar a usar o bot enviando `/start` numa conversa
  privada ou num grupo onde o bot foi adicionado. O sistema cria ou reativa o cadastro do chat
  (pessoa ou grupo) a partir da identidade do Telegram, sem aprovação manual.
- **FR-002**: O sistema MUST limitar a quantidade de processos que cada chat (pessoa ou grupo)
  acompanha. O limite é configurável, com padrão de 10.
- **FR-002a**: Em grupos, `/watch`, `/unwatch`, `/pause` e `/resume` MUST ser aceitos apenas de
  administradores do grupo. Os demais comandos são aceitos de qualquer membro.
- **FR-002b**: O bot MUST reconhecer comandos no formato `/comando@NomeDoBot`, ignorar comandos
  dirigidos a outros bots e ignorar atualizações de canais.
- **FR-002c**: Quando o Telegram migrar um grupo para supergrupo, o sistema MUST transferir o
  cadastro e as assinaturas para o novo identificador.
- **FR-003**: O sistema MUST aceitar atualizações do Telegram somente quando acompanhadas da
  credencial secreta configurada, e MUST processar cada atualização uma única vez.

**Comandos**

- **FR-004**: O bot MUST oferecer os comandos `/start`, `/help`, `/watch`, `/unwatch`, `/list`,
  `/status`, `/check`, `/pause`, `/resume` e `/history`, e registrá-los no menu de comandos do
  Telegram.
- **FR-005**: `/watch` MUST validar e normalizar o número do processo, reaproveitar o
  monitoramento existente quando o processo já é acompanhado por alguém e, quando for um
  processo novo, fazer a primeira leitura para registrar o estado inicial antes de confirmar o
  monitoramento ao usuário.
- **FR-006**: A primeira leitura de processos novos e as verificações de `/check` MUST ser feitas
  pelo monitor em segundo plano. A resposta imediata ao comando nunca espera a consulta ao site
  do CADE.
- **FR-007**: `/check` MUST respeitar um intervalo mínimo entre verificações do mesmo processo,
  configurável com padrão de 5 minutos. Dentro desse intervalo, responde com o estado salvo e o
  tempo restante.
- **FR-008**: `/pause` e `/resume` MUST valer apenas para o usuário que os enviou. Um processo só
  deixa de ser consultado quando nenhum usuário (de nenhum canal) o acompanha ativamente.
- **FR-009**: `/history` MUST mostrar as últimas movimentações detectadas do processo, até um
  limite configurável com padrão de 5.
- **FR-010**: Comandos que recebem um número de processo (menos `/watch`) MUST atuar apenas
  sobre processos que o próprio usuário acompanha.
- **FR-011**: Mensagens sem comando reconhecido MUST receber uma resposta com a ajuda resumida.

**Alertas**

- **FR-012**: Toda mudança detectada num processo MUST gerar um alerta no Telegram para cada
  chat que acompanha o processo e não o pausou, usando o mesmo registro de notificações,
  tentativas e limite de retentativas dos canais existentes.
- **FR-013**: Alertas MUST ser escritos em português, em linguagem natural, com rótulo do
  processo, resumo da mudança, documentos novos (quando houver) e link público.
- **FR-014**: Quando o Telegram informar que o usuário bloqueou o bot ou que o bot foi removido
  do grupo, o sistema MUST marcar o chat como inalcançável e parar de enviar para ele até que
  alguém envie `/start` novamente nesse chat.
- **FR-015**: Os canais de e-mail e WhatsApp MUST continuar funcionando sem mudança de
  comportamento para os assinantes atuais.

- **FR-015a**: O bot MUST oferecer `/last_update <processo>` para qualquer membro do chat que
  acompanha o processo. O comando envia a última atualização conhecida (protocolo mais recente,
  última mudança detectada, link do processo) e o arquivo desse protocolo quando ele puder ser
  obtido. O processo não é verificado de novo.
- **FR-015b**: Os alertas no Telegram MUST incluir o arquivo dos documentos novos (PDF ou outro
  formato servido pelo SEI) sempre que o download for possível dentro do limite configurado.
  Arquivos compactados ou maiores que o limite seguem apenas como link.

**Operação**

- **FR-016**: O operador MUST conseguir registrar o endereço de recebimento do bot no Telegram,
  consultar seu estado e removê-lo com um comando administrativo.
- **FR-017**: O painel administrativo MUST permitir ver os usuários do Telegram, seus processos
  acompanhados e as ações pendentes do bot.
- **FR-018**: O bot inteiro MUST poder ser desligado por configuração. Desligado, ele não aceita
  atualizações e não cria alertas no Telegram.

### Key Entities

- **Chat do Telegram**: conversa em que o bot atua, que pode ser uma pessoa (privado) ou um grupo.
  Tem identificador do Telegram, tipo (privado ou grupo), nome exibido e um indicador de
  alcançável ou bloqueado/removido. Está ligado a um assinante do sistema, o que permite
  reaproveitar o fluxo de notificações.
- **Assinatura de processo** (existente, ampliada): vínculo entre assinante e processo. Ganha a
  preferência de receber pelo Telegram e o indicador de pausada pelo usuário.
- **Atualização recebida do Telegram**: registro de cada atualização já processada, para
  garantir o processamento único.
- **Ação pendente do bot**: pedido que depende de consulta ao site do CADE (primeira leitura de
  `/watch`, verificação de `/check`), com quem pediu, qual processo, quando foi pedido e quando
  foi concluído.
- **Notificação** (existente): ganha o canal Telegram.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Uma pessoa ou grupo sem cadastro consegue sair do `/start` para um monitoramento ativo, com
  a última movimentação exibida, em menos de 2 minutos e sem ajuda da equipe.
- **SC-002**: Todo comando recebe uma primeira resposta do bot em até 5 segundos, inclusive os
  que dependem de consulta ao site do CADE.
- **SC-003**: Alertas de mudança chegam ao Telegram em até 1 ciclo do worker depois da detecção,
  para 100% dos usuários ativos daquele processo.
- **SC-004**: Nenhum processo é consultado no site do CADE mais de uma vez dentro do intervalo
  mínimo de `/check`, independente de quantos usuários peçam.
- **SC-005**: Entregas duplicadas de uma mesma atualização do Telegram geram uma única resposta
  e um único efeito.
- **SC-006**: Nenhum usuário consegue ver status, histórico ou controle de processos que não
  acompanha.
- **SC-007**: A suíte de testes existente de notificações por e-mail e WhatsApp continua
  passando sem alteração.

## Assumptions

- O bot funciona em conversas privadas e em grupos/supergrupos. Canais de broadcast ficam fora
  do escopo.
- Em grupos, a verificação de administrador é feita consultando o Telegram no momento do
  comando. Nenhuma lista de administradores é armazenada.
- Cada chat do Telegram (pessoa ou grupo) vira um assinante próprio. Vincular um usuário do Telegram a um
  assinante já cadastrado pelo painel (e-mail/WhatsApp) fica fora do escopo da v1.
- Formato aceito de processo: número SEI do CADE `NNNNN.NNNNNN/AAAA-DD` (com normalização de
  espaços e pontuação ausente) ou link público do SEI. Outros órgãos ficam fora do escopo.
- Os intervalos da cadência periódica continuam os do projeto (mínimo de 25 minutos por
  processo). O `/check` é a única exceção controlada, limitada pelo intervalo mínimo próprio, e
  os pedidos simultâneos são agrupados numa única consulta.
- O endereço público HTTPS da aplicação no Render está disponível para receber as atualizações
  do Telegram (webhook).
- O bot é criado pelo dono do projeto no @BotFather, e o token fica apenas nas variáveis de
  ambiente.
- Depende da feature 005 (PostgreSQL), já que web e worker no Render compartilham o banco.
