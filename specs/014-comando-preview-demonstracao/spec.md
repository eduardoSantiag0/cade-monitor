# Feature Specification: Comando /preview — demonstração para portfólio

**Feature Branch**: `014-comando-preview-demonstracao`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "O CADE Monitor deve ser pensado também como projeto de portfólio, permitindo que recrutadores, desenvolvedores ou outras pessoas interessadas entendam rapidamente seu funcionamento sem configurar processos reais, informar dados pessoais ou aguardar uma nova movimentação real no CADE. Implementar um comando `/preview` no bot do Telegram que executa uma demonstração controlada do fluxo principal do sistema (detecção de mudança → notificação), usando um processo fictício, reaproveitando o máximo possível da lógica real da aplicação, sem tocar o SEI/CADE nem disparar notificação real."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver uma demonstração completa do fluxo principal (Priority: P1)

Qualquer pessoa que converse com o bot do Telegram (sem precisar já acompanhar nenhum processo)
envia `/preview` e recebe, em segundos, uma mensagem mostrando como o CADE Monitor se comporta
quando detecta uma mudança num processo: um processo fictício claramente identificado como
demonstração, o andamento anterior, o novo andamento "detectado", a data/hora da detecção, um
resumo da alteração, e por quais canais uma notificação real seria enviada nesse caso.

**Why this priority**: é o objetivo inteiro da feature — sem isso não há demonstração alguma.

**Independent Test**: enviar `/preview` para o bot (ambiente de teste) e conferir que a resposta
contém todos os elementos esperados (processo fictício, andamento anterior, nova movimentação,
resumo, canais), claramente rotulados como demonstração, chegando em poucos segundos.

**Acceptance Scenarios**:

1. **Given** um usuário qualquer no chat privado do bot (com ou sem processo já monitorado),
   **When** envia `/preview`, **Then** recebe uma resposta com um processo fictício, o andamento
   anterior, a nova movimentação, data/hora, resumo, e os canais de notificação — tudo rotulado
   como demonstração — sem esperar nenhum tempo de scraping real.
2. **Given** o comando `/preview` já foi executado antes, **When** é executado de novo, **Then**
   a demonstração roda normalmente de novo (idempotente — não acumula processos fictícios
   duplicados nem estados inconsistentes a cada execução).
3. **Given** o comando é executado num grupo do Telegram (não só no privado), **When** `/preview`
   é enviado, **Then** funciona da mesma forma (não é uma ação de gerenciamento restrita a
   administradores — é só uma demonstração, sem efeito sobre o que o grupo acompanha).

---

### User Story 2 - Confiar que a demonstração nunca mexe em dado real (Priority: P1)

Um usuário já usa o bot para acompanhar processos reais. Ao rodar `/preview`, esse uso real não é
afetado de forma alguma: nenhum processo real é criado/alterado, nenhuma notificação real (e-mail/
WhatsApp/Telegram) é enviada a ninguém, nenhuma requisição é feita ao SEI/CADE, e nenhum dado
pessoal é solicitado ou exibido.

**Why this priority**: é a condição que torna a feature segura de existir em produção, ao lado do
sistema real — sem essa garantia, a demonstração seria um risco, não um recurso.

**Independent Test**: rodar `/preview` várias vezes seguidas com processos reais monitorados no
mesmo banco, e confirmar por inspeção de log/banco que: (a) nenhuma requisição HTTP externa foi
feita, (b) nenhum e-mail/WhatsApp/Telegram real foi disparado, (c) nenhum `MonitoredProcess` real
(além do único processo fictício de demonstração, sempre o mesmo) foi criado ou alterado.

**Acceptance Scenarios**:

1. **Given** o sistema tem processos reais monitorados e assinantes reais cadastrados, **When**
   `/preview` é executado, **Then** nenhum desses processos ou assinantes reais é lido, alterado,
   ou usado de qualquer forma na resposta.
2. **Given** a demonstração roda, **When** analisado o tráfego de rede do processo da aplicação
   durante a execução, **Then** nenhuma requisição HTTP para `sei.cade.gov.br`, `sinc.cade.gov.br`,
   `in.gov.br`, ou qualquer outro serviço externo acontece.
3. **Given** a demonstração roda, **When** os canais reais de notificação (e-mail/WhatsApp) são
   inspecionados, **Then** nenhum envio real foi disparado por eles.

---

### User Story 3 - Entender o sistema em minutos pelo README (Priority: P2)

Uma pessoa que chega ao repositório do GitHub pela primeira vez lê o README e entende, em poucos
minutos, o que o CADE Monitor faz e como ver isso funcionando na prática, sem precisar configurar
nada — sabe que existe um comando de demonstração, como executá-lo, e o que esperar como resposta.

**Why this priority**: é o que conecta a feature ao objetivo declarado de portfólio — a demonstração
só cumpre esse papel se for fácil de descobrir a partir do README.

**Independent Test**: pedir para alguém sem contexto prévio do projeto ler só a seção do README
sobre o modo de demonstração e dizer, com as próprias palavras, o que o `/preview` faz.

**Acceptance Scenarios**:

1. **Given** o README do projeto, **When** lido por alguém novo no repositório, **Then** essa
   pessoa encontra uma seção específica explicando o modo de demonstração, como executar `/preview`,
   e um exemplo do formato de resposta.

---

### Edge Cases

- `/preview` enviado por alguém que nunca interagiu com o bot antes (sem `TelegramChat`/
  `Subscriber` prévio): funciona normalmente — a demonstração não depende de o usuário já ter
  qualquer cadastro no sistema.
- `/preview` enviado repetidamente em sequência rápida: cada execução responde de forma
  independente e consistente, sem acumular processos/mudanças fictícios extras no banco a cada
  chamada.
- Bot indisponível/erro ao responder no Telegram: mesmo tratamento de erro já existente para
  qualquer outro comando — não é uma exigência nova desta feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST expor um comando `/preview` no bot do Telegram, disponível para
  qualquer usuário (chat privado ou grupo), sem exigir que o usuário já acompanhe algum processo.
- **FR-002**: Ao executar `/preview`, o sistema MUST usar um processo fictício de demonstração,
  claramente identificável como tal (rótulo/número de processo fictício, nunca um número real de
  processo do CADE), reaproveitado entre execuções (não cria um novo processo fictício a cada
  chamada).
- **FR-003**: O sistema MUST simular uma nova movimentação nesse processo fictício, com um
  andamento anterior e uma nova movimentação, sem consultar nenhuma fonte externa para obtê-los.
- **FR-004**: O sistema MUST reaproveitar a lógica real de detecção de mudança da aplicação
  (comparação/diff entre o andamento anterior e o novo) para gerar o resumo da alteração exibido —
  não uma versão reimplementada ou hardcoded do texto de resumo.
- **FR-005**: O sistema MUST reaproveitar a lógica real de formatação de notificação da aplicação
  para gerar o conteúdo de exemplo exibido, mostrando por quais canais uma notificação real seria
  enviada nesse caso.
- **FR-006**: O sistema MUST NOT realizar nenhuma requisição de rede a serviços externos (SEI,
  CADE, Diário Oficial, ou qualquer outro) em qualquer parte da execução do comando.
- **FR-007**: O sistema MUST NOT enviar nenhuma notificação real por e-mail, WhatsApp ou Telegram
  como resultado da demonstração — o conteúdo de exemplo é exibido na própria resposta do comando,
  nunca despachado por um canal real.
- **FR-008**: O sistema MUST NOT criar, alterar ou de qualquer forma afetar processos monitorados
  reais, assinantes reais, ou preferências reais do usuário que executou o comando.
- **FR-009**: O sistema MUST exibir, na resposta, ao menos: identificação do processo fictício
  (rotulado como demonstração), andamento anterior, nova movimentação, data/hora da "detecção",
  resumo da alteração, e os canais pelos quais uma notificação normalmente seria enviada.
- **FR-010**: O sistema MUST responder ao `/preview` em poucos segundos, sem qualquer espera
  equivalente a um ciclo real de verificação.
- **FR-011**: O README MUST incluir uma seção explicando o modo de demonstração, como executar
  `/preview`, e um exemplo do formato de resposta.
- **FR-012**: A lógica da demonstração MUST viver num caso de uso dedicado, separado do
  handler/parsing do comando do bot — o handler do comando MUST apenas iniciar esse caso de uso e
  devolver o texto de resposta que ele produzir.

### Key Entities *(include if feature involves data)*

- **Processo fictício de demonstração**: um único `MonitoredProcess` reservado, sempre o mesmo
  entre execuções, com dados claramente fictícios, isolado do ciclo real de monitoramento (nunca
  verificado pelo worker, nunca com assinante real).
- **Cenário de demonstração**: o par (andamento anterior, nova movimentação) usado para simular a
  mudança — dados fixos/fictícios, não obtidos de nenhuma fonte externa.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `/preview` responde em até 3 segundos em 100% das execuções em teste automatizado
  (sem depender de qualquer chamada de rede).
- **SC-002**: Em 100% das execuções de teste automatizado, nenhuma chamada HTTP externa é feita
  (verificável por mock estrito que falha o teste se qualquer função de rede for invocada).
- **SC-003**: Em 100% das execuções de teste automatizado, nenhum canal de notificação real
  (e-mail/WhatsApp/Telegram) é invocado para envio.
- **SC-004**: Rodar `/preview` 10 vezes seguidas produz sempre a mesma identificação de processo
  fictício (nunca cria um segundo processo fictício) e nunca deixa o banco num estado
  inconsistente (verificável contando registros do processo fictício antes/depois).
- **SC-005**: Uma pessoa sem contexto prévio do projeto consegue explicar o que o CADE Monitor faz
  depois de ler só a seção de demonstração do README e rodar `/preview` uma vez (validável por
  teste manual de legibilidade).

## Assumptions

- O comando é aberto a qualquer usuário (não exige assinatura/cadastro prévio) e não é uma "ação
  de gerenciamento" no sentido já usado pelo bot (`MANAGEMENT_COMMANDS`) — não precisa de
  restrição de administrador em grupos.
- "Reaproveitar o máximo possível da lógica real" é interpretado como: reaproveitar a lógica de
  diff/resumo de mudança e a lógica de formatação de mensagem de notificação já existentes
  (funções puras, sem I/O) — não reaproveitar literalmente o caminho que faz requisição HTTP ao
  SEI (`get_snapshot`) nem o caminho que baixa documentos novos (`collect_new_documents`), já que
  ambos dependem de rede externa por natureza; esses dois pontos são substituídos por dados fixos
  de demonstração, conforme FR-006.
- O processo fictício de demonstração é um registro real no banco (não puramente em memória a cada
  chamada), mas permanentemente isolado do ciclo de monitoramento real (nunca `status=ativo` para
  fins de checagem periódica) — permite reaproveitar os modelos/serviços reais de mudança
  (`DetectedChange` etc.) sem risco de interferência.
- Notificação de exemplo é só exibida como texto na resposta do `/preview` — não persiste um
  registro de notificação "pendente" que o worker real poderia, por engano, tentar enviar depois.
