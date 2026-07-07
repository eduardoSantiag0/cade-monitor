# Feature Specification: CADE Monitor Platform

**Feature Branch**: `001-cade-monitor`

**Created**: 2026-07-07

**Status**: Draft

**Input**: Platform-level specification covering process monitoring, change detection, notifications, human review, and operational tooling for CADE/SEI public processes.

---

## User Scenarios & Testing _(mandatory)_

### User Story 1 — Monitoramento Automático de Processos (Priority: P1)

O sistema monitora periodicamente processos públicos do CADE/SEI cadastrados, detecta mudanças no conteúdo das páginas e registra essas mudanças com resumo legível por humanos.

**Why this priority**: É o núcleo de valor da plataforma. Sem monitoramento automático e detecção de mudanças, nenhuma outra funcionalidade faz sentido.

**Independent Test**: Pode ser testado inteiramente via management commands (`run_worker`, inspeção direta do banco) sem UI: cadastrar um processo, simular variação de conteúdo, confirmar `DetectedChange` gerado com resumo humanizado.

**Acceptance Scenarios**:

1. **Given** um processo monitorado cujo intervalo de checagem venceu, **When** o worker processa esse processo, **Then** o sistema faz requisição HTTP GET à URL pública, extrai texto visível (sem scripts/estilos), calcula hash SHA-256, compara com o snapshot anterior e, se diferente, registra um `DetectedChange` com diff textual e resumo humanizado.

2. **Given** o conteúdo da página não mudou desde a última checagem, **When** o worker processa esse processo, **Then** nenhum `DetectedChange` é criado e o `CheckRun` registra resultado "sem mudança".

3. **Given** uma mudança detectada em um processo com andamentos ou protocolos estruturados, **When** o diff é calculado, **Then** o diff estruturado destaca linhas adicionadas/removidas nos blocos de andamentos e protocolos separadamente do diff genérico do restante da página.

4. **Given** a URL de um processo retorna erro HTTP (4xx/5xx) ou timeout de rede, **When** o worker tenta monitorar, **Then** o erro é registrado no `CheckRun`, o processo não é marcado como alterado, e o erro é logado com nível WARNING com URL e código de resposta.

5. **Given** o worker está em execução, **When** há múltiplos processos com intervalos vencidos, **Then** eles são processados sequencialmente (um por vez), respeitando a restrição de writer único do SQLite.

---

### User Story 2 — Cadastro de Processos (Priority: P1)

O operador cadastra processos públicos para monitoramento, podendo fornecer uma URL direta ou um número de protocolo que o sistema resolve automaticamente para a URL pública no SEI.

**Why this priority**: Sem cadastro de processos não há nada a monitorar. Está no mesmo nível crítico que o monitoramento.

**Independent Test**: Pode ser testado isoladamente: cadastrar processo por URL e verificar que aparece na lista; cadastrar por número de protocolo e verificar que a URL é resolvida antes de salvar.

**Acceptance Scenarios**:

1. **Given** o operador acessa o formulário de cadastro de processo, **When** fornece uma URL pública válida do SEI, **Then** o processo é salvo com a URL fornecida e status "ativo" com intervalo padrão.

2. **Given** o operador fornece um número de protocolo no formato `NNNNN.NNNNNN/AAAA-DD` (ex: `08700.005905/2026-38`), **When** o processo é submetido, **Then** o sistema consulta o SEI para resolver o número para a URL pública correspondente e salva o processo com essa URL.

3. **Given** um número de protocolo não encontrado no SEI, **When** o sistema tenta resolver, **Then** exibe mensagem de erro clara ao operador e não cria o processo.

4. **Given** o operador cadastra um processo com intervalo de checagem menor que 25 minutos, **When** submete o formulário, **Then** o sistema rejeita a entrada com mensagem indicando o intervalo mínimo permitido.

5. **Given** um processo já cadastrado com a mesma URL, **When** o operador tenta cadastrar novamente, **Then** o sistema previne duplicata e informa o operador.

---

### User Story 3 — Notificação de Assinantes (Priority: P2)

Assinantes cadastrados em um processo recebem notificações por e-mail e/ou WhatsApp quando uma mudança é detectada, com mensagem em linguagem natural descrevendo o que mudou.

**Why this priority**: Notificação é o canal de entrega de valor aos usuários finais. Sem notificação, os assinantes precisariam verificar o painel manualmente.

**Independent Test**: Pode ser testado criando um assinante, simulando um `DetectedChange` e verificando que tentativas de notificação são registradas com o conteúdo esperado — sem depender de UI ou worker completo.

**Acceptance Scenarios**:

1. **Given** um assinante inscrito em um processo com canal e-mail ativo, **When** uma mudança é detectada nesse processo, **Then** o sistema envia e-mail para o endereço do assinante com resumo humanizado da mudança, registra a tentativa em `NotificationAttempt` e marca o resultado (sucesso/falha).

2. **Given** um assinante inscrito com canal WhatsApp ativo, **When** uma mudança é detectada, **Then** o sistema envia mensagem via Evolution API para o número do assinante com resumo humanizado em português.

3. **Given** um assinante com ambos os canais habilitados (e-mail e WhatsApp), **When** uma mudança é detectada, **Then** notificações são enviadas em ambos os canais sequencialmente.

4. **Given** a Evolution API retorna erro no envio, **When** o sistema tenta notificar via WhatsApp, **Then** a falha é registrada em `NotificationAttempt` com o erro, e a notificação por e-mail (se configurada) ainda é tentada independentemente.

5. **Given** um assinante sem canal de notificação ativo, **When** uma mudança é detectada, **Then** nenhuma tentativa de envio é realizada para esse assinante.

---

### User Story 4 — Revisão Humana de Mudanças (Priority: P2)

O operador revisa mudanças detectadas e as classifica para filtrar falsos positivos e destacar alterações importantes.

**Why this priority**: A revisão humana é o mecanismo de controle de qualidade que distingue mudanças relevantes de ruído, aumentando a confiabilidade do sistema.

**Independent Test**: Pode ser testado independentemente: criar `DetectedChange`, atualizar classificação via interface, confirmar novo status persistido.

**Acceptance Scenarios**:

1. **Given** uma mudança detectada sem classificação (status padrão), **When** o operador acessa o detalhe da mudança e seleciona "Importante", **Then** o status é atualizado para `importante` e a alteração é refletida imediatamente na lista de mudanças.

2. **Given** uma mudança detectada, **When** o operador a classifica como "Falso positivo", **Then** o status é atualizado para `falso_positivo` e a mudança é visualmente diferenciada na lista.

3. **Given** uma mudança detectada, **When** o operador a classifica como "Ignorado", **Then** o status é atualizado para `ignorado` e futuras notificações do mesmo tipo não reenviam a mesma mudança.

4. **Given** o operador acessa o detalhe de uma mudança, **When** a página é carregada, **Then** exibe o diff textual completo, o resumo humanizado, a data/hora da detecção e o status de classificação atual.

5. **Given** uma mudança classificada como "Analisado", **When** outra mudança nova é detectada no mesmo processo, **Then** a nova mudança é listada separadamente com status pendente de classificação.

---

### User Story 5 — Painel Web (Priority: P3)

O operador acessa um painel web para visualizar processos monitorados, histórico de mudanças, assinantes e notificações enviadas.

**Why this priority**: O painel é a interface principal de visibilidade operacional, mas as funcionalidades core funcionam sem ele (via management commands e Django Admin).

**Independent Test**: Pode ser testado verificando que cada página do painel carrega sem erro, exibe dados corretos do banco e responde dentro do tempo esperado.

**Acceptance Scenarios**:

1. **Given** o operador acessa o dashboard, **When** a página é carregada, **Then** exibe resumo com: total de processos monitorados, mudanças detectadas nas últimas 24h, próximas checagens agendadas e processos com erros recentes.

2. **Given** o operador acessa a lista de processos, **When** a página é carregada, **Then** exibe todos os processos com nome, URL, último check, status e indicação visual se há mudanças não revisadas.

3. **Given** o operador acessa o detalhe de um processo, **When** a página é carregada, **Then** exibe histórico completo de mudanças com classificação, lista de assinantes e configuração de intervalo.

4. **Given** o operador acessa a lista de assinantes, **When** a página é carregada, **Then** exibe todos os assinantes com canais de notificação ativos e número de inscrições em processos.

5. **Given** o operador acessa a lista de notificações, **When** a página é carregada, **Then** exibe histórico de notificações enviadas com status de entrega (sucesso/falha) e canal utilizado.

---

### User Story 6 — Operações de Manutenção (Priority: P3)

O sistema executa tarefas periódicas de manutenção: envio de digest diário e limpeza de snapshots antigos.

**Why this priority**: São operações de suporte que reduzem ruído e controlam crescimento do banco de dados, mas não afetam o monitoramento em si.

**Independent Test**: Pode ser testado executando os management commands diretamente e verificando os efeitos no banco de dados.

**Acceptance Scenarios**:

1. **Given** processos com mudanças detectadas nas últimas 24h, **When** o comando `generate_daily_digest` é executado, **Then** assinantes com inscrições ativas recebem digest consolidado com resumo das mudanças do dia, agrupadas por processo.

2. **Given** o banco de dados contém snapshots de páginas mais antigos que o período de retenção configurado, **When** o comando `cleanup_snapshots` é executado, **Then** snapshots expirados são removidos, liberando espaço, e o número de registros excluídos é logado.

3. **Given** nenhuma mudança nas últimas 24h, **When** `generate_daily_digest` é executado, **Then** nenhum digest é enviado e o log registra "sem mudanças para notificar".

---

### Edge Cases

- O que acontece quando a URL de um processo monitorado passa a retornar redirecionamento (3xx)?
- Como o sistema se comporta se o banco SQLite atingir o limite de locks durante a checagem concurrent com a UI?
- O que acontece se o conteúdo da página mudar estruturalmente (ex: o SEI reformula o layout) invalidando o diff estruturado?
- Como o sistema lida com páginas que mudam a cada request (timestamps dinâmicos embutidos no HTML)?
- O que acontece se a Evolution API self-hosted ficar indisponível por período prolongado?
- Como o worker se recupera após reinicialização inesperada do container?

---

## Requirements _(mandatory)_

### Functional Requirements

**Cadastro e Resolução de Processos**

- **FR-001**: O sistema DEVE permitir cadastrar processos públicos fornecendo URL direta ou número de protocolo no formato CADE/SEI.
- **FR-002**: O sistema DEVE resolver números de protocolo para URLs públicas via busca no SEI antes de salvar o processo.
- **FR-003**: O sistema DEVE rejeitar cadastro de processos com intervalo de checagem inferior a 1500 segundos (25 minutos).
- **FR-004**: O sistema DEVE impedir cadastro duplicado de processos com a mesma URL.
- **FR-005**: O sistema DEVE permitir editar o intervalo de checagem e status ativo/inativo de processos já cadastrados.

**Monitoramento e Detecção de Mudanças**

- **FR-006**: O sistema DEVE extrair apenas o texto visível das páginas monitoradas, excluindo conteúdo de tags `<script>`, `<style>` e atributos não-textuais.
- **FR-007**: O sistema DEVE normalizar o texto extraído (espaços, quebras de linha) e calcular hash SHA-256 para comparação.
- **FR-008**: O sistema DEVE comparar o hash atual com o hash do snapshot anterior; se diferente, registrar um `DetectedChange`.
- **FR-009**: O sistema DEVE calcular diff estruturado separando blocos de andamentos e protocolos quando a estrutura for reconhecida.
- **FR-010**: O sistema DEVE registrar todo `CheckRun` com timestamp, resultado e eventuais erros, independentemente de mudança detectada.
- **FR-011**: O sistema DEVE processar processos vencidos sequencialmente, um por vez, para preservar a integridade do banco SQLite.
- **FR-012**: O sistema DEVE manter o worker em execução contínua como management command, com loop de sleep configurável entre ciclos.

**Notificações**

- **FR-013**: O sistema DEVE enviar notificações por e-mail via SMTP configurável quando uma mudança é detectada e o assinante tem esse canal ativo.
- **FR-014**: O sistema DEVE enviar notificações via Evolution API (WhatsApp) quando uma mudança é detectada e o assinante tem esse canal ativo.
- **FR-015**: O sistema DEVE registrar cada tentativa de notificação em `NotificationAttempt` com canal, status e erro (se houver).
- **FR-016**: O sistema DEVE enviar notificações em linguagem natural em português, descrevendo o que mudou de forma legível por não técnicos.
- **FR-017**: O sistema DEVE enviar notificações sequencialmente (um canal por vez, um assinante por vez) no MVP.

**Revisão Humana**

- **FR-018**: O sistema DEVE permitir classificar `DetectedChange` com um dos status: `analisado`, `importante`, `ignorado`, `falso_positivo`.
- **FR-019**: O sistema DEVE exibir o diff textual completo e o resumo humanizado na tela de detalhe de uma mudança.

**Assinantes**

- **FR-020**: O sistema DEVE permitir cadastrar assinantes com nome, e-mail e/ou número de WhatsApp.
- **FR-021**: O sistema DEVE permitir associar e desassociar assinantes de processos específicos (ProcessSubscription).
- **FR-022**: O sistema DEVE permitir ativar/desativar individualmente cada canal de notificação por assinante.

**Painel Web**

- **FR-023**: O painel DEVE exibir dashboard com métricas operacionais (processos ativos, mudanças recentes, erros).
- **FR-024**: O painel DEVE listar processos, mudanças, assinantes e notificações com navegação entre as seções.
- **FR-025**: O painel DEVE ser acessível sem autenticação de usuário final no MVP (uso interno/intranet).

**Manutenção**

- **FR-026**: O sistema DEVE fornecer comando `generate_daily_digest` que consolida mudanças do dia e notifica assinantes.
- **FR-027**: O sistema DEVE fornecer comando `cleanup_snapshots` que remove snapshots além do período de retenção configurado.
- **FR-028**: Todos os management commands DEVEM ter `--help` descritivo e tratamento de erros com log explícito.

---

### Key Entities

- **MonitoredProcess**: Processo público do CADE/SEI monitorado. Atributos principais: URL, número de protocolo (opcional), intervalo de checagem, status ativo/inativo, última checagem, próxima checagem agendada.
- **ProcessTag**: Tag associada a um processo para categorização.
- **CheckRun**: Registro de uma execução de checagem de processo. Atributos: timestamp, resultado (sem mudança / mudança detectada / erro), mensagem de erro se aplicável.
- **PageSnapshot**: Snapshot do conteúdo textual extraído de uma página. Atributos: hash SHA-256, conteúdo normalizado, timestamp de captura.
- **DetectedChange**: Mudança detectada entre dois snapshots consecutivos. Atributos: diff textual, diff estruturado (andamentos/protocolos), resumo humanizado, status de classificação humana.
- **AppSetting**: Configurações globais da aplicação armazenadas no banco (ex: intervalo padrão, período de retenção de snapshots).
- **Subscriber**: Assinante que recebe notificações. Atributos: nome, e-mail, número de WhatsApp, canais ativos.
- **ProcessSubscription**: Associação entre assinante e processo monitorado.
- **Notification**: Registro de notificação gerada para uma mudança detectada.
- **NotificationAttempt**: Tentativa de envio de notificação por canal específico. Atributos: canal (email/whatsapp), status, timestamp, mensagem de erro se falhou.

---

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: Mudanças em processos monitorados são detectadas e registradas dentro de um ciclo de monitoramento completo após a alteração ocorrer na fonte.
- **SC-002**: Notificações são entregues a assinantes em até 5 minutos após detecção de mudança, em condições normais de rede.
- **SC-003**: O sistema opera continuamente em VM com ≤ 512 MB de RAM disponível sem erros de memória ou degradação de performance em idle.
- **SC-004**: O worker processa um ciclo completo de todos os processos vencidos sem travar ou perder registros, mesmo após reinicialização inesperada do container.
- **SC-005**: 100% das tentativas de notificação (sucesso e falha) são rastreáveis via `NotificationAttempt`, permitindo auditoria completa.
- **SC-006**: Operadores conseguem classificar uma mudança detectada (revisar) em menos de 30 segundos pelo painel web.
- **SC-007**: O painel web carrega qualquer página principal (dashboard, lista de processos, detalhes) em menos de 3 segundos com até 200 processos cadastrados.
- **SC-008**: O comando `cleanup_snapshots` mantém o banco de dados abaixo de um tamanho operacional sustentável para a VM, sem interromper o monitoramento em curso.

---

## Assumptions

- A aplicação é de uso interno/intranet operada por um pequeno número de operadores; não há requisito de autenticação multi-usuário no MVP.
- Apenas páginas **públicas** do CADE/SEI são monitoradas; nenhuma credencial de acesso ao SEI é necessária ou armazenada.
- A Evolution API é self-hosted e operada pelo mesmo operador da plataforma; sua disponibilidade é responsabilidade externa ao escopo do CADE Monitor.
- O período de retenção padrão de snapshots é configurável via `AppSetting`; o valor padrão razoável é 30 dias.
- O digest diário é disparado manualmente via cron externo (ex: crontab do host ou Docker Compose `command`) chamando o management command.
- O número máximo prático de processos monitorados para a VM alvo é dezenas (não centenas de milhares); queries sem paginação pesada são aceitáveis no MVP.
- O formato estruturado de diff (andamentos/protocolos) é derivado do padrão de layout do SEI e pode precisar de ajuste se o SEI reformular seu HTML.
- O intervalo padrão de checagem é 1800 segundos (30 minutos), acima do mínimo obrigatório de 1500 segundos.
- Todos os textos de UI, mensagens de notificação e logs voltados ao operador são em português do Brasil.
- Não há requisito de internacionalização (i18n) ou suporte a múltiplos idiomas.
