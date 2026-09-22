# Feature Specification: Confiabilidade Operacional do Monitoramento

**Feature Branch**: `004-confiabilidade-operacional`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Aumentar a confiabilidade operacional do monitoramento: alertar o admin quando o worker travar ou a sessão do WhatsApp na Evolution API cair, pausar automaticamente um processo após falhas consecutivas de scraping em vez de tentar para sempre, e registrar auditoria de quem disparou envios manuais de notificação pelo painel."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Alertar quando o worker de monitoramento para (Priority: P1)

Como operador do CADE Monitor, quero ser avisado quando o processo de checagem contínua (`run_worker`) parar de rodar, para poder reiniciá-lo antes que os assinantes percebam que pararam de receber atualizações.

**Why this priority**: Hoje, se o worker travar ou cair, a única forma de perceber é um assinante reclamar de silêncio prolongado ou alguém ler o log manualmente. Isso é o cenário de falha mais silencioso e mais caro do sistema — o valor central de um "monitor" é justamente notificar sobre mudanças; um monitor que parou de monitorar sem avisar ninguém falha no seu propósito básico.

**Independent Test**: Pode ser testado interrompendo manualmente o processo `run_worker` em um ambiente de teste e confirmando que, após o intervalo configurado, um alerta chega ao operador por e-mail.

**Acceptance Scenarios**:

1. **Given** o worker rodando normalmente e registrando sinais de vida a cada ciclo, **When** ele para de registrar esses sinais por mais tempo do que o limite configurado, **Then** o operador recebe um alerta por e-mail informando a última vez que o worker esteve ativo.
2. **Given** um alerta de worker parado já enviado, **When** o worker volta a registrar sinais de vida normalmente, **Then** nenhum alerta repetido é enviado até uma nova interrupção ocorrer.

---

### User Story 2 - Distinguir falha transitória de bloqueio persistente ao checar um processo (Priority: P1)

Como operador, quero que o sistema tente novamente um processo que falhou por um motivo transitório (timeout, instabilidade de rede) antes de desistir, mas que também pare de insistir automaticamente — e me avise — quando a falha for persistente (ex.: bloqueio/captcha), em vez de continuar tentando para sempre em silêncio ou de desistir depois de um único erro.

**Why this priority**: Durante a análise desta spec, foi identificado que o comportamento atual já interrompe a checagem automática de um processo após uma única falha (o processo passa a `status=error`, e a fila de checagens devidas só considera processos `status=active`) — ou seja, hoje uma falha isolada (um timeout pontual, por exemplo) já tira silenciosamente um processo do radar, sem qualquer aviso, até alguém notar e reativá-lo manualmente. Esse é um risco tão sério quanto "tentar para sempre": o sistema já pode estar cego para processos importantes agora mesmo, sem que ninguém saiba.

**Independent Test**: Pode ser testado simulando falhas consecutivas de checagem de um processo e confirmando que (a) as primeiras falhas dentro do limite configurado não tiram o processo do ciclo automático de checagem, e (b) só ao ultrapassar o limite o processo para de ser checado automaticamente E um alerta é enviado ao operador.

**Acceptance Scenarios**:

1. **Given** um processo que falha em uma checagem por um motivo transitório, **When** o número de falhas consecutivas ainda está abaixo do limite configurado, **Then** o processo continua sendo considerado na fila normal de checagens futuras, sem intervenção humana.
2. **Given** um processo que atinge o limite configurado de falhas consecutivas, **When** a última tentativa falha, **Then** o processo para de ser checado automaticamente e o operador recebe um alerta explicando o motivo e o número de tentativas.
3. **Given** um processo pausado automaticamente por falhas consecutivas, **When** ele volta a responder com sucesso após uma checagem manual, **Then** ele volta a fazer parte do ciclo automático normalmente, com o contador de falhas consecutivas zerado.

---

### User Story 3 - Alertar quando a sessão do WhatsApp desconecta (Priority: P2)

Como operador, quero ser avisado quando os envios via WhatsApp começarem a falhar de forma consistente (sinal de que a sessão da Evolution API caiu e precisa de um novo QR code), para reconectar antes que muitas notificações se acumulem sem serem entregues.

**Why this priority**: É um caso mais específico do que a falha genérica de envio já tratada por retentativa — hoje essas falhas só aparecem no log e na lista de notificações pendentes, sem nenhum aviso ativo. É P2 porque o e-mail continua funcionando como canal de fallback enquanto isso não é resolvido, então o impacto é menor que as histórias P1.

**Independent Test**: Pode ser testado simulando falhas consecutivas de envio por WhatsApp acima do limite configurado e confirmando que um alerta chega ao operador por e-mail (nunca por WhatsApp, já que esse é o canal potencialmente indisponível).

**Acceptance Scenarios**:

1. **Given** um número configurado de falhas consecutivas de envio por WhatsApp em um curto intervalo, **When** esse número é atingido, **Then** o operador recebe um alerta por e-mail sugerindo verificar a conexão da sessão do WhatsApp.
2. **Given** um alerta de desconexão do WhatsApp já enviado, **When** um envio por WhatsApp volta a ter sucesso, **Then** nenhum alerta repetido é enviado até uma nova sequência de falhas ocorrer.

---

### User Story 4 - Auditoria de envios manuais de notificação (Priority: P2)

Como operador, quero saber qual usuário disparou um envio manual de notificação (teste de e-mail/WhatsApp, aviso manual, reenvio da última atualização) pelo painel, e quando, para ter rastreabilidade sobre comunicações enviadas em nome do sistema a assinantes reais.

**Why this priority**: Hoje qualquer usuário autenticado pode disparar esses envios sem nenhum registro de autoria — não impede o uso, mas impede investigar depois "quem mandou isso e quando" se um assinante questionar uma mensagem recebida. É P2 porque não é um risco de disponibilidade como as histórias anteriores, é uma lacuna de rastreabilidade.

**Independent Test**: Pode ser testado disparando cada uma das ações de envio manual existentes e confirmando que um registro de auditoria consultável no painel mostra usuário, ação, processo-alvo, data/hora e resultado.

**Acceptance Scenarios**:

1. **Given** um usuário autenticado dispara um envio manual de notificação para um processo, **When** a ação é concluída (com sucesso ou falha), **Then** um registro de auditoria com usuário, ação, processo, data/hora e resultado fica disponível para consulta no painel.

---

### Edge Cases

- O que acontece se o próprio worker que deveria alertar sobre si mesmo for o processo que travou? O sinal de vida MUST ser verificado por um componente separado do laço principal do worker (ex.: o scheduler já existente, que roda em outro processo), não pelo próprio worker tentando se autodiagnosticar.
- O que acontece se o canal de e-mail (usado para os alertas operacionais) também estiver fora do ar? Está fora do escopo desta spec cobrir um canal de alerta de último recurso caso o e-mail falhe — isso é uma limitação aceita.
- O que acontece com o contador de falhas consecutivas de um processo se ele for pausado manualmente por um usuário no meio da sequência de falhas? O contador MUST ser reiniciado quando o processo for reativado manualmente, para não pausar automaticamente de novo por falhas que já aconteceram antes da intervenção humana.
- Dois alertas diferentes (worker parado e sessão do WhatsApp caída) podem ocorrer ao mesmo tempo — cada um MUST ser tratado e notificado de forma independente, sem que um mascare o outro.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O worker de monitoramento (`run_worker`) MUST registrar um sinal de vida (heartbeat) verificável de forma persistente a cada ciclo completo.
- **FR-002**: O sistema MUST verificar periodicamente, por um componente independente do worker, se o sinal de vida está mais antigo do que um limite configurável e, se estiver, MUST notificar um operador designado por e-mail.
- **FR-003**: O sistema MUST NOT enviar alertas repetidos de "worker parado" enquanto a condição de falha continuar a mesma — um novo alerta só é enviado após o worker voltar a funcionar e parar novamente.
- **FR-004**: O sistema MUST contar falhas consecutivas de checagem por processo e continuar considerando o processo na fila normal de checagens automáticas enquanto esse contador estiver abaixo de um limite configurável — revertendo o comportamento atual, em que uma única falha já remove o processo do ciclo automático.
- **FR-005**: Ao atingir o limite configurável de falhas consecutivas, o sistema MUST parar de checar automaticamente aquele processo e MUST notificar o operador designado, informando o processo, o motivo da última falha e o número de tentativas.
- **FR-006**: Um processo interrompido automaticamente por falhas consecutivas MUST ser visualmente distinguível, no painel, de um processo pausado manualmente por um usuário.
- **FR-007**: O contador de falhas consecutivas de um processo MUST ser zerado tanto por uma checagem bem-sucedida quanto por uma reativação manual feita por um usuário.
- **FR-008**: O sistema MUST contar falhas consecutivas de envio por WhatsApp (não por e-mail) dentro de uma janela configurável e, ao atingir um limite configurável, MUST notificar o operador designado por e-mail sugerindo verificar a sessão da Evolution API.
- **FR-009**: O sistema MUST NOT usar o próprio canal WhatsApp para alertar sobre uma possível falha do canal WhatsApp.
- **FR-010**: O sistema MUST registrar, para cada disparo manual de notificação feito por um usuário autenticado através do painel (teste de e-mail, teste de WhatsApp, aviso manual, reenvio da última atualização), o usuário responsável, o processo-alvo, a data/hora e o resultado (sucesso/falha/contagens).
- **FR-011**: Esse registro de auditoria MUST ficar disponível para consulta por usuários autenticados dentro do painel, não apenas no arquivo de log do servidor.
- **FR-012**: Os destinatários dos alertas operacionais (worker parado, sessão do WhatsApp caída, processo auto-pausado) MUST ser configuráveis separadamente da lista de assinantes que recebem notificações de mudança de processo — são públicos diferentes.

### Key Entities

- **Sinal de vida do worker**: Registro do horário do último ciclo completo executado pelo worker de monitoramento, usado para detectar paralisação.
- **Contador de falhas consecutivas** (por processo monitorado): Quantidade de checagens malsucedidas em sequência para um mesmo processo, resetado por sucesso ou por reativação manual.
- **Registro de auditoria de envio manual**: Usuário, ação, processo-alvo, data/hora e resultado de cada disparo manual de notificação feito pelo painel.
- **Destinatário de alerta operacional**: Contato (e-mail) que recebe avisos de falha operacional do sistema, distinto dos assinantes de mudanças de processo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Uma paralisação do worker gera um alerta ao operador em até o dobro do intervalo configurado de verificação, sem exigir leitura manual de log.
- **SC-002**: Uma falha isolada e transitória de checagem não interrompe o monitoramento automático de nenhum processo (0% de processos pausados automaticamente por uma única falha).
- **SC-003**: Um processo com bloqueio persistente para de ser checado automaticamente e gera um alerta em até N tentativas configuradas, nunca continuando indefinidamente sem aviso.
- **SC-004**: Uma sequência de falhas de envio por WhatsApp gera um alerta por e-mail ao operador, nunca deixando o problema visível apenas na lista de notificações pendentes.
- **SC-005**: 100% dos disparos manuais de notificação feitos pelo painel ficam associados a um usuário identificável, consultável sem acesso ao servidor.

## Assumptions

- O "operador designado" para receber alertas é configurado por um endereço de e-mail nas variáveis de ambiente/configurações do sistema, reaproveitando o canal de e-mail já existente — nenhum novo canal de alerta (Slack, PagerDuty, SMS) é introduzido, para não conflitar com os Princípios V e VIII da constituição do projeto (provedor único de mensageria; sem over-engineering).
- Os limites numéricos (intervalo de heartbeat, número de falhas consecutivas para auto-pausa, número de falhas de WhatsApp para alerta de desconexão) são configuráveis via variável de ambiente, seguindo o padrão já usado pelo restante do projeto (`.env` + `EnvSettings`), com um valor padrão razoável definido durante o planejamento técnico.
- A verificação do sinal de vida do worker é feita por um componente que já roda separadamente (o container/processo `scheduler` já existente no `docker-compose.yml`), não por um novo serviço dedicado — alinhado ao Princípio I (minimizar processos novos).
- Esta spec assume que a mudança de comportamento descrita na User Story 2 (não pausar mais após uma única falha) é desejável; se, na prática, mesmo uma única falha de um tipo específico (ex.: bloqueio explícito por CAPTCHA) já deve pausar imediatamente sem esperar N tentativas, essa distinção fica para o planejamento técnico detalhar por tipo de erro.
