# Feature Specification: PostgreSQL gerenciado como banco principal

**Feature Branch**: `005-postgres-render`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Criar abstrações para funcionar com PostgreSQL versão 18, que passa a ser o banco principal. O Postgres roda no Render (instância gerenciada, com URL interna para serviços dentro do Render e URL externa para acesso de fora). O SQLite continua apenas como fallback para desenvolvimento local e testes. Base para a feature seguinte (bot do Telegram), que já deve nascer rodando sobre o Postgres."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rodar a aplicação em produção sobre o banco gerenciado (Priority: P1)

Como operador do CADE Monitor, quero que o painel web e o worker de monitoramento usem o banco
PostgreSQL gerenciado no Render, configurado só por variável de ambiente, para ter um banco
durável, com backup gerenciado e acessível por mais de um serviço sem depender de um arquivo
local num volume Docker.

**Why this priority**: É o objetivo central da feature e pré-requisito do bot do Telegram
(feature 006), que roda no Render e precisa compartilhar o mesmo banco com o worker. Sem isso,
nada mais da feature entrega valor.

**Independent Test**: Configurar a conexão do banco gerenciado num ambiente limpo, aplicar o
esquema, cadastrar um processo pelo painel e executar uma checagem. O processo, o snapshot e o
registro da checagem devem aparecer no banco gerenciado.

**Acceptance Scenarios**:

1. **Given** a conexão com o banco gerenciado configurada no ambiente, **When** a aplicação
   sobe, **Then** todas as leituras e escritas (painel, worker, comandos administrativos) vão
   para o banco gerenciado.
2. **Given** um banco gerenciado vazio, **When** o operador aplica o esquema da aplicação,
   **Then** todas as tabelas são criadas sem erro e a aplicação fica utilizável.
3. **Given** o painel web e o worker rodando ao mesmo tempo sobre o banco gerenciado, **When** o
   worker grava resultados de checagem enquanto um usuário navega no painel, **Then** nenhum dos
   dois sofre erro de bloqueio ou espera perceptível.
4. **Given** a conexão configurada com credenciais inválidas ou banco inacessível, **When** a
   aplicação sobe ou executa uma operação, **Then** ela falha com uma mensagem clara indicando
   problema de conexão com o banco, sem expor a senha em logs.

---

### User Story 2 - Desenvolver e testar localmente sem o banco gerenciado (Priority: P1)

Como desenvolvedor, quero que, sem nenhuma configuração de banco, a aplicação e a suíte de testes
continuem funcionando com o banco local em arquivo, para não depender de rede nem de credenciais
de produção no dia a dia.

**Why this priority**: Protege o fluxo de desenvolvimento e a suíte de testes existente. Um erro
aqui quebraria todo o ciclo de trabalho da equipe, e por isso tem a mesma prioridade da
História 1.

**Independent Test**: Num clone limpo e sem a variável de conexão definida, rodar a suíte de
testes completa e subir o servidor de desenvolvimento. Tudo deve funcionar como antes da feature.

**Acceptance Scenarios**:

1. **Given** nenhuma conexão de banco gerenciado configurada, **When** a aplicação sobe, **Then**
   ela usa o banco local em arquivo exatamente como hoje, incluindo os ajustes de desempenho
   atuais.
2. **Given** o banco gerenciado configurado, **When** a aplicação sobe, **Then** os ajustes
   específicos do banco local não são aplicados.
3. **Given** a suíte de testes existente, **When** ela roda contra qualquer um dos dois bancos,
   **Then** todos os testes passam.

---

### User Story 3 - Migrar os dados existentes para o banco gerenciado (Priority: P2)

Como operador, quero levar os processos, assinantes, histórico de mudanças e notificações que já
existem no banco local para o banco gerenciado, para trocar de banco sem perder o histórico nem
recadastrar tudo.

**Why this priority**: Importante para a virada de produção, mas é uma operação única e manual.
A aplicação entrega valor num banco novo mesmo sem ela.

**Independent Test**: A partir de uma cópia do banco local com dados reais, seguir o
procedimento documentado e comparar as contagens de registros por tipo entre origem e destino.

**Acceptance Scenarios**:

1. **Given** um banco local com dados, **When** o operador segue o procedimento documentado de
   migração, **Then** o banco gerenciado contém os mesmos processos, assinantes, assinaturas,
   mudanças detectadas e notificações, com as mesmas contagens.
2. **Given** os dados migrados, **When** o worker executa o próximo ciclo, **Then** os processos
   existentes são checados a partir da linha de base migrada, sem gerar alertas falsos de
   "primeira leitura" ou de mudança.

---

### User Story 4 - Backup adequado ao banco em uso (Priority: P3)

Como operador, quero que o comando de backup se comporte corretamente conforme o banco em uso,
para não ter uma rotina agendada falhando em silêncio ou dando falsa sensação de segurança.

**Why this priority**: O provedor gerenciado já oferece backup próprio. Este item evita
confusão operacional e erros no agendador diário, mas não bloqueia o uso.

**Independent Test**: Executar o comando de backup com cada um dos dois bancos configurados e
verificar o resultado e a mensagem exibida.

**Acceptance Scenarios**:

1. **Given** o banco local em uso, **When** o operador executa o backup, **Then** o
   comportamento atual é mantido (cópia do arquivo com rotação).
2. **Given** o banco gerenciado em uso, **When** o operador executa o backup, **Then** o comando
   gera um dump quando a ferramenta de dump está disponível. Caso contrário, informa claramente
   que o backup é responsabilidade do provedor gerenciado e termina sem erro, sem travar o
   agendador diário.

---

### Edge Cases

- A conexão com o banco gerenciado cai no meio de um ciclo do worker: o ciclo atual registra o
  erro e o worker tenta reconectar no ciclo seguinte, sem precisar ser reiniciado manualmente.
- Conexões ociosas encerradas pelo provedor: a aplicação detecta a conexão inválida antes de
  usá-la e abre uma nova, sem erro para o usuário.
- A URL de conexão aponta para o endereço interno do provedor, mas o acesso vem de fora (ex.:
  máquina do desenvolvedor): a falha de conexão deve ser clara, e a documentação explica quando
  usar cada endereço.
- Limite de conexões simultâneas do plano contratado: web e worker juntos devem ficar dentro do
  limite.
- A variável de conexão está definida mas vazia ou mal formatada: a aplicação falha na subida
  com mensagem de configuração inválida, sem cair silenciosamente no banco local.
- Texto com caracteres especiais ou muito longo vindo do SEI: deve ser armazenado sem truncar
  nem corromper, igual ao banco local.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST usar o banco PostgreSQL gerenciado como banco principal sempre que
  uma URL de conexão estiver configurada no ambiente.
- **FR-002**: O sistema MUST usar o banco local em arquivo quando nenhuma URL de conexão estiver
  configurada, preservando o comportamento atual (incluindo os ajustes de desempenho do banco
  local).
- **FR-003**: Os ajustes específicos do banco local MUST ser aplicados apenas quando o banco
  local estiver em uso.
- **FR-004**: As credenciais do banco MUST vir exclusivamente do ambiente. Nenhuma credencial
  real pode aparecer no repositório, nos arquivos de exemplo ou em logs.
- **FR-005**: Conexões ao banco gerenciado feitas de fora da rede do provedor MUST usar conexão
  criptografada. O modo de criptografia MUST ser configurável.
- **FR-006**: O sistema MUST reaproveitar conexões entre requisições e validar conexões antes do
  uso, recuperando-se sozinho de conexões encerradas pelo provedor.
- **FR-007**: Uma URL de conexão presente mas inválida MUST impedir a subida da aplicação com
  mensagem de erro de configuração clara.
- **FR-008**: O esquema completo da aplicação (todas as migrations existentes) MUST ser aplicável
  a um banco gerenciado vazio sem erros nem ajustes manuais.
- **FR-009**: O sistema MUST documentar um procedimento de migração dos dados do banco local para
  o banco gerenciado, preservando identificadores e relacionamentos.
- **FR-010**: O comando de backup MUST se adaptar ao banco em uso: copiar o arquivo no banco
  local, e no banco gerenciado gerar um dump ou informar claramente que o backup é gerenciado
  pelo provedor, sem retornar erro.
- **FR-011**: A documentação de configuração (arquivo de exemplo do ambiente e README) MUST
  explicar a nova variável de conexão, a diferença entre o endereço interno e o externo do
  provedor e o fallback para o banco local.
- **FR-012**: A suíte de testes MUST passar contra os dois bancos.

### Key Entities

- **Configuração de conexão do banco**: URL única que identifica servidor, porta, nome do banco,
  usuário, senha e parâmetros de conexão (ex.: modo de criptografia). Pode vir em duas
  variantes: endereço interno (dentro do provedor) e externo (acesso pela internet).
- **Dados de domínio existentes** (processos monitorados, assinantes, assinaturas, checagens,
  snapshots, mudanças detectadas, documentos, notificações, configurações do sistema): o modelo
  não muda. Só muda onde esses dados ficam guardados.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Com o banco gerenciado configurado, 100% das operações do painel, do worker e dos
  comandos administrativos persistem no banco gerenciado, e nenhuma escreve no banco local.
- **SC-002**: Em um ambiente sem configuração de banco, a suíte de testes completa passa sem
  nenhuma alteração nos testes existentes.
- **SC-003**: A suíte de testes completa também passa com o banco gerenciado configurado.
- **SC-004**: Após a migração, as contagens de registros de cada tipo de dado são idênticas entre
  a origem e o destino.
- **SC-005**: No primeiro ciclo após a migração, nenhum alerta falso (de "primeira leitura" ou de
  mudança) é enviado aos assinantes.
- **SC-006**: Após uma queda temporária do banco, o worker volta a checar processos no máximo um
  ciclo depois de o banco voltar, sem intervenção manual.
- **SC-007**: Uma busca por credenciais reais no repositório (senha, usuário ou host completo da
  instância) retorna zero ocorrências.

## Assumptions

- A instância gerenciada é PostgreSQL 18 no Render. Web e worker rodam no Render e usam o
  endereço interno. Acesso a partir da máquina do desenvolvedor usa o endereço externo com
  conexão criptografada.
- A senha compartilhada durante o planejamento será rotacionada pelo operador antes de ir para
  produção, e a nova senha só existirá nas variáveis de ambiente do provedor e no `.env` local
  (que não é versionado).
- O plano contratado no Render suporta pelo menos as conexões simultâneas de 1 processo web
  (1 worker, 2 threads) mais 1 worker de monitoramento. Se for o plano gratuito, o operador está
  ciente de que ele tem prazo de expiração e deve confirmar o plano antes da virada de produção.
- O modelo de dados não muda nesta feature. As novas tabelas do bot do Telegram ficam para a
  feature 006.
- A migração de dados é uma operação única e manual, feita pelo operador numa janela de
  manutenção com o worker parado. Não é necessário sincronizar os dois bancos continuamente.
- O cache opcional de hash em Redis continua funcionando igual, independente do banco.
