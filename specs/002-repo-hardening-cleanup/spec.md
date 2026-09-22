# Feature Specification: Hardening e Limpeza Técnica do Repositório

**Feature Branch**: `002-repo-hardening-cleanup`

**Created**: 2026-09-22

**Status**: Clarified — pronta para `/speckit.plan`

**Input**: User description: "Corrigir problemas críticos e de alta prioridade encontrados em revisão de código: dados binários do Postgres commitados no git, README apagado, SECRET_KEY inseguro em produção, código morto duplicado (cademon/ e wa-bot/), Makefile duplicado, dependências sem pin, ausência de CI, duplicação de views de notificação manual, download desnecessário de anexo para WhatsApp, e conflito não documentado do uso de Redis com a constituição do projeto."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Repositório seguro e íntegro para qualquer colaborador (Priority: P1)

Como mantenedor do CADE Monitor, quero que qualquer pessoa possa clonar o repositório, entender o que é o projeto e rodá-lo localmente sem herdar dados binários de banco de dados, segredos de produção mal configurados ou documentação ausente.

**Why this priority**: Estes são riscos de segurança e de continuidade do projeto (dados versionados incorretamente podem vazar, corromper o histórico ou impedir clones eficientes; um `SECRET_KEY` inseguro em produção é uma falha de segurança direta; a ausência de README é um bloqueador de onboarding). Sem isso resolvido, qualquer outro trabalho no projeto herda risco.

**Independent Test**: Pode ser validado clonando o repositório do zero em uma máquina limpa, subindo a stack com `DEBUG=false` e um `.env` sem `SECRET_KEY`, e confirmando que (a) nenhum arquivo binário de banco aparece no histórico do clone, (b) a aplicação recusa subir sem uma chave segura explícita, e (c) o README explica o projeto e os passos de setup.

**Acceptance Scenarios**:

1. **Given** um clone novo do repositório, **When** o colaborador lista os arquivos versionados em `data/evolution-postgres/`, **Then** nenhum arquivo binário de banco de dados é retornado.
2. **Given** o repositório na branch principal, **When** o colaborador abre a raiz do projeto, **Then** existe um `README.md` com visão geral, instruções de setup e link para `specs/`.
3. **Given** `DEBUG=false` e nenhuma variável `SECRET_KEY` definida no ambiente, **When** a aplicação é iniciada, **Then** o processo falha imediatamente com uma mensagem explícita, em vez de subir com a chave padrão insegura.

---

### User Story 2 - Uma única fonte de verdade para o código de scraping e notificação (Priority: P1)

Como mantenedor, quero que exista apenas uma implementação ativa de scraping/notificação, para que novos colaboradores (ou eu mesmo, no futuro) não percam tempo descobrindo qual código é o real e qual é legado.

**Why this priority**: Duas implementações divergentes do mesmo domínio (`cademon/` vs `apps/monitoring/`) são uma fonte garantida de bugs por edição no lugar errado, e aumentam a superfície de auditoria de segurança sem benefício.

**Independent Test**: Pode ser validado buscando por importações de `cademon` fora de código de teste/arquivo e confirmando que a suíte de testes ativa não depende de módulos legados para passar.

**Acceptance Scenarios**:

1. **Given** o código-fonte do projeto, **When** se busca por referências de import ao pacote `cademon` ou ao serviço `wa-bot`, **Then** nenhuma referência aparece fora de um local claramente identificado como arquivo histórico (ou elas deixam de existir).
2. **Given** a suíte de testes, **When** ela é executada, **Then** nenhum teste depende de `cademon/scraper.py` para passar.

---

### User Story 3 - Build reprodutível e verificado automaticamente (Priority: P2)

Como mantenedor, quero que toda alteração enviada ao repositório rode a suíte de testes automaticamente, e que as versões de dependências instaladas sejam sempre as mesmas, para não descobrir regressões apenas em produção.

**Why this priority**: Sem CI, a suíte de ~1400 linhas de testes existente não protege ninguém na prática. Sem pin de dependências, um `pip install` em dois momentos diferentes pode instalar código diferente.

**Independent Test**: Pode ser validado abrindo um Pull Request com uma mudança que quebra um teste existente e observando que o PR é marcado como falho automaticamente; e reinstalando `requirements.txt` em um ambiente limpo duas vezes, confirmando que as versões resolvidas são idênticas.

**Acceptance Scenarios**:

1. **Given** um Pull Request com uma alteração que quebra um teste, **When** o PR é aberto, **Then** um pipeline de CI roda a suíte de testes e reporta falha no PR sem intervenção manual.
2. **Given** `requirements.txt` (ou lockfile equivalente), **When** o ambiente é instalado em duas máquinas diferentes na mesma data, **Then** as versões instaladas dos pacotes são idênticas.

---

### User Story 4 - Envio manual de notificações consistente e eficiente (Priority: P3)

Como mantenedor, quero que a lógica de envio manual de e-mail/WhatsApp (teste, aviso manual, última atualização) seja escrita uma única vez e que o canal WhatsApp não baixe documentos que não vai efetivamente enviar como conteúdo, para reduzir bugs de manutenção e desperdício de banda/memória.

**Why this priority**: É um problema de qualidade e eficiência confirmado, mas de impacto operacional menor que os itens P1/P2 — não bloqueia uso nem expõe dado sensível.

**Independent Test**: Pode ser validado comparando a contagem de linhas duplicadas entre as quatro views de envio manual antes/depois, e instrumentando uma chamada de envio de anexo por WhatsApp para confirmar que o conteúdo binário do documento não é mais baixado quando apenas a URL é usada no envio.

**Acceptance Scenarios**:

1. **Given** as quatro views de envio manual (`process_send_test_email`, `process_notify_subscribers`, `process_send_test_whatsapp`, `process_send_latest_update`), **When** o código é inspecionado, **Then** a lógica de iterar assinantes e contar envios/falhas por canal existe em um único lugar compartilhado.
2. **Given** uma notificação de anexo via WhatsApp que só precisa da URL pública do documento, **When** o envio é disparado, **Then** o conteúdo binário do documento não é baixado pelo servidor apenas para ser descartado.

---

### Edge Cases

- Como o histórico antigo do git não será reescrito, clones existentes continuam com os ~68MB de binários já commitados em seu `.git` local; apenas o `git ls-files` (árvore de trabalho atual) deixa de listá-los. Isso é aceito como débito técnico, não como bug desta feature.
- O que acontece se a suíte de testes falhar no CI por depender de uma variável de ambiente/segredo que só existe localmente? O pipeline deve rodar com valores de teste/dummy, nunca com segredos reais de produção.
- O que acontece se um processo em produção já estiver rodando com o `SECRET_KEY` inseguro no momento em que a validação estrita for ativada? O deploy deve falhar de forma visível (não silenciosa) para forçar a correção antes de servir tráfego.
- O que acontece com o histórico de mensagens do WhatsApp já enviadas caso a Evolution API não consiga buscar a URL original do documento sem sessão/referer (risco já existente, não introduzido por esta mudança)? Deve continuar caindo no fluxo de retentativa (`pending_retry`) já existente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST parar de versionar os arquivos de dados binários do Postgres usados pela Evolution API (`data/evolution-postgres/`), removendo-os do índice do git (`git rm -r --cached`) e atualizando o `.gitignore` para impedir que arquivos desse diretório voltem a ser rastreados. **Decisão**: o histórico antigo do git NÃO será reescrito nesta spec — os commits já existentes continuam contendo os binários; apenas commits futuros deixam de incluí-los. Reescrita de histórico (BFG/git-filter-repo) fica registrada como débito técnico aceito, não como requisito desta feature.
- **FR-002**: O repositório MUST conter um `README.md` na raiz descrevendo o propósito do projeto, como configurá-lo (`.env`, Docker Compose) e como rodar os testes, antes de qualquer novo commit ser aceito na branch principal.
- **FR-003**: A aplicação MUST recusar iniciar quando `DEBUG=false` e `SECRET_KEY` não estiver definido explicitamente no ambiente ou for igual ao valor padrão de exemplo, falhando de forma explícita e imediata na subida do processo (não em runtime, no meio de uma requisição).
- **FR-004**: O código legado duplicado do domínio de scraping/notificação (pacote `cademon/` e serviço `wa-bot/`) MUST ser removido completamente da branch principal, incluindo `tests/test_scraper.py` (que só existe para testar o módulo legado) e quaisquer scripts (`scripts/rebuild_venv.sh`, `scripts/install_whatsapp_bot.sh`, `scripts/keepalive_whatsapp.sh`) que só fazem sentido para esse código. **Decisão**: remoção total, não arquivamento — o código permanece acessível via histórico do git (`git log`) caso seja necessário consultar depois.
- **FR-005**: O `Makefile` MUST conter cada target definido exatamente uma vez, sem blocos de conteúdo duplicados.
- **FR-006**: As dependências de produção em `requirements.txt` MUST ser fixadas em versões exatas (ou geridas por um lockfile determinístico), de forma que duas instalações em datas diferentes resultem no mesmo conjunto de versões.
- **FR-007**: O projeto MUST ter um pipeline de integração contínua que executa a suíte de testes automaticamente a cada push e a cada Pull Request contra a branch principal, e sinaliza falha de forma visível no PR.
- **FR-008**: As views de envio manual de notificação em `apps/processes/views.py` MUST reutilizar uma única implementação compartilhada para iterar assinaturas e contabilizar envios/falhas por canal, eliminando a duplicação hoje presente entre as quatro views equivalentes.
- **FR-009**: O fluxo de envio de anexo por WhatsApp MUST deixar de baixar o conteúdo binário completo de um documento quando esse conteúdo não é usado no envio (apenas a URL pública é enviada à Evolution API); a validação de tamanho do arquivo MUST ocorrer sem exigir download completo do documento sempre que uma alternativa mais barata (ex.: cabeçalho de tamanho da resposta) estiver disponível.
- **FR-010**: Falhas não tratadas no worker de monitoramento (`run_worker`) e no scheduler MUST ser reportadas a um serviço de rastreamento de erros externo ao log local, preservando o log de arquivo existente como registro secundário.
- **FR-011**: O uso de Redis como cache de hash de processo (`PROCESS_HASH_REDIS_ENABLED`, já presente no código e em `requirements.txt`) MUST ter seu status de conformidade com a constituição do projeto resolvido antes do fechamento desta feature. **Decisão**: a constituição foi emendada (v1.0.0 → v1.1.0, ver `.specify/memory/constitution.md`) para permitir formalmente o Redis como exceção única de cache distribuído, condicionada à aplicação continuar funcional com o cache desabilitado. Nenhuma mudança de código é necessária para este FR — `apps/monitoring/cache.py` já degrada corretamente para o hash em `MonitoredProcess.last_hash` quando o Redis está indisponível ou desabilitado; resta apenas confirmar essa cobertura em teste automatizado caso ainda não exista.

### Key Entities

*Não aplicável — esta feature é estrutural/operacional e não introduz novas entidades de domínio.*

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um `git ls-files` sobre o diretório `data/evolution-postgres/` não retorna nenhum arquivo após a mudança.
- **SC-002**: Uma pessoa nova consegue entender o propósito do projeto e colocá-lo para rodar localmente lendo apenas o `README.md`, em até 10 minutos.
- **SC-003**: 100% das tentativas de iniciar a aplicação em modo produção sem `SECRET_KEY` seguro resultam em falha explícita na subida do processo, não em execução silenciosa com valor inseguro.
- **SC-004**: 100% dos pushes e Pull Requests contra a branch principal disparam a suíte de testes automaticamente, sem passo manual.
- **SC-005**: Duas instalações de `requirements.txt` em datas diferentes resultam no mesmo conjunto de versões instaladas.
- **SC-006**: A quantidade de linhas duplicadas entre as quatro views de envio manual de notificação cai em pelo menos 60% em relação ao estado atual.
- **SC-007**: O volume de bytes baixados do documento original por envio de anexo WhatsApp cai a praticamente zero nos casos em que o conteúdo baixado não é efetivamente enviado.
- **SC-008**: Um erro não tratado no worker ou no scheduler aparece em uma ferramenta de rastreamento de erros externa em até poucos minutos da ocorrência, sem depender de alguém ler o arquivo de log manualmente.

## Assumptions

- Existe (ou é aceitável criar) uma conta gratuita/self-hosted de rastreamento de erros compatível com o Princípio I da constituição (baixo consumo de recursos), para atender FR-010.
- A plataforma de CI a ser usada é GitHub Actions, por já ser o serviço Git do projeto (`.github/` já existe na árvore do repositório) — sem introduzir uma ferramenta de CI externa adicional.
- "Restaurar o README" (FR-002) assume que o conteúdo anterior pode ser recuperado do histórico do git (`git log -- README.md` mostra commits anteriores); caso o conteúdo recuperado esteja desatualizado, ele deve ser revisado, não apenas restaurado cegamente.
- Esta spec cobre apenas os itens críticos/altos/médios de higiene de repositório e qualidade de código já identificados; não cobre a questão de escalabilidade de SQLite sob múltiplos escritores, pois essa é uma decisão arquitetural deliberada e permanente do Princípio IV da constituição do projeto, não um defeito a corrigir.
- Novas features de produto (auto-monitoramento de processos relacionados, arquivo de documentos, importação em lote, exportação, alertas operacionais, API pública, canais adicionais de mensageria) estão fora do escopo desta spec e MUST ser tratadas em specs de feature separadas, conforme a convenção de "um feature por spec" do Spec Kit.
