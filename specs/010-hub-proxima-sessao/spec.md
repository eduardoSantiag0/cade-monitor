# Feature Specification: Próxima sessão de julgamento no dashboard

**Feature Branch**: `010-hub-proxima-sessao`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "Hub: dados da tela inicial (ex. sessão de julgamento ao vivo do CADE)". Porte do comportamento do módulo `cademon/hub.py` do projeto irmão "Mesk", com escopo reduzido para caber no dashboard interno (autenticado) já existente do cade-monitor — ver Assumptions para o que foi deliberadamente deixado de fora e por quê.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver a próxima sessão de julgamento do CADE ao abrir o dashboard (Priority: P1)

Um usuário autenticado do cade-monitor abre a página inicial do dashboard e vê, num cartão de
destaque, a data e o título da próxima sessão de julgamento do CADE (ex. "05 de outubro — 269ª
Sessão Ordinária"), incluindo a de hoje se houver uma. A informação vem de uma fonte pública do
CADE, atualizada periodicamente em segundo plano — a página nunca busca a fonte externa na hora
do carregamento.

**Why this priority**: É o valor central da feature — sem isso não há cartão de sessão algum. A
História 2 (link da pauta) é um complemento sobre a mesma sessão já exibida.

**Independent Test**: com uma fixture do calendário de sessões do CADE representando sessões
futuras e passadas, popular o cache via o refresh em segundo plano e confirmar que o dashboard
mostra a sessão futura mais próxima (inclusive a de hoje), nunca uma já passada.

**Acceptance Scenarios**:

1. **Given** o cache de sessões contém uma sessão daqui a 5 dias e outra ocorrida há 2 dias,
   **When** o dashboard é carregado, **Then** o cartão mostra a sessão futura (daqui a 5 dias),
   nunca a passada.
2. **Given** hoje é o dia de uma sessão cadastrada, **When** o dashboard é carregado, **Then** o
   cartão mostra a sessão de hoje.
3. **Given** o cache de sessões está vazio ou expirado e a atualização em segundo plano ainda não
   rodou (ou a fonte externa falhou), **When** o dashboard é carregado, **Then** a página é
   exibida normalmente, sem o cartão de sessão (nunca um erro visível ao usuário).
4. **Given** o cache já tem sessões futuras, **When** o dashboard é carregado múltiplas vezes em
   sequência, **Then** nenhuma chamada à fonte externa acontece durante essas cargas de página (a
   view lê só o cache já persistido).

---

### User Story 2 - Ver o link da pauta da próxima sessão, quando já publicada (Priority: P2)

Além da data/título, quando a pauta (documento PDF publicado pelo CADE) da próxima sessão já foi
disponibilizada, o cartão traz um link direto para ela. Antes de publicada, o cartão aparece sem
o link (não um link quebrado).

**Why this priority**: Complementa a História 1 com um dado que nem sempre está disponível (a
pauta sai dias antes da sessão) — por isso é uma história separada e de prioridade menor: o
cartão já é útil sem ela.

**Independent Test**: com uma fixture da página anual de pautas do CADE contendo o PDF da sessão
em exibição, confirmar que o link aparece; com uma fixture sem esse PDF, confirmar que o cartão
aparece sem link e sem erro.

**Acceptance Scenarios**:

1. **Given** a próxima sessão exibida é a 269ª de 2026 e a fixture da página anual de pautas
   contém um PDF de nome compatível para essa sessão, **When** o dashboard é carregado,
   **Then** o cartão mostra um link para esse PDF.
2. **Given** a pauta da próxima sessão ainda não foi publicada (fonte não traz o PDF), **When** o
   dashboard é carregado, **Then** o cartão mostra a sessão normalmente, sem nenhum link ou aviso
   de erro.

---

### Edge Cases

- Fonte externa do calendário de sessões fora do ar durante a atualização em segundo plano: o
  cache anterior (se ainda válido) continua servindo o cartão; se não houver cache válido, o
  cartão simplesmente não aparece — nunca trava a atualização em segundo plano nem o carregamento
  do dashboard.
- Nenhuma sessão futura no calendário lido (ex.: fim de ano, calendário do ano seguinte ainda não
  publicado): o cartão não aparece, sem erro.
- Duas atualizações em segundo plano muito próximas uma da outra (ex.: reinício do worker): a
  cadência mínima entre buscas evita repetir a mesma chamada à fonte em sequência.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST manter, em segundo plano, um cache com a lista de sessões de
  julgamento do CADE (data + título), atualizado periodicamente a partir de uma fonte pública do
  CADE — nunca buscado durante o carregamento da página do dashboard.
- **FR-002**: O sistema MUST exibir, no dashboard, a sessão futura mais próxima do cache
  (inclusive a de hoje), e MUST NOT exibir sessões já passadas.
- **FR-003**: Quando não houver nenhuma sessão futura no cache (cache vazio, expirado sem
  atualização bem-sucedida, ou sem sessão futura), o sistema MUST carregar o dashboard
  normalmente, sem exibir o cartão de sessão e sem exibir erro ao usuário.
- **FR-004**: O sistema MUST respeitar uma cadência mínima entre tentativas de atualização do
  cache de sessões (evitar buscar a fonte a cada ciclo do worker).
- **FR-005**: O sistema MUST manter, em segundo plano, um cache do link da pauta (PDF) da sessão
  em exibição, atualizado a partir de uma fonte pública do CADE — nunca buscado durante o
  carregamento da página.
- **FR-006**: O sistema MUST exibir o link da pauta no cartão quando disponível no cache, e MUST
  exibir o cartão sem link (não um link quebrado) quando a pauta ainda não estiver publicada.
- **FR-007**: Falha ao buscar qualquer uma das duas fontes externas MUST NOT interromper a
  atualização em segundo plano de outros dados do sistema, nem aparecer como erro visível ao
  usuário — apenas o cache correspondente permanece com o valor anterior (ou vazio).

### Key Entities *(include if feature involves data)*

- **Sessão de julgamento**: data e título de uma sessão do CADE, como listada no calendário
  público de sessões.
- **Pauta da sessão**: link (URL) do documento PDF da pauta de uma sessão específica, quando já
  publicado.
- **Cache do hub**: par chave/valor com validade (TTL), compartilhado entre o processo web e o
  worker em segundo plano, usado para as duas fontes acima.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: O carregamento do dashboard nunca depende de uma chamada de rede a uma fonte
  externa do CADE — o tempo de resposta da página não é afetado pela disponibilidade dessas
  fontes (verificável por teste automatizado sem rede real).
- **SC-002**: Em qualquer cenário de fixture testado (sessão futura presente, ausente, pauta
  publicada ou não, fonte externa falhando), o dashboard sempre carrega sem erro visível.
- **SC-003**: A atualização em segundo plano nunca busca a mesma fonte externa mais de uma vez
  dentro do intervalo mínimo configurado, mesmo com múltiplos ciclos do worker nesse intervalo.

## Assumptions

- **Escopo reduzido em relação ao `hub.py` original do Mesk** (decisão de engenharia, não requer
  aprovação do dono do projeto — ver plan.md/research.md para o racional completo):
  - **Fora de escopo nesta versão**: status de transmissão ao vivo no YouTube (`youtube.com` é um
    domínio de terceiro fora do escopo atual do Princípio II; o valor para um painel interno de
    equipe é menor que o do calendário de sessões) e a cidade do visitante via geolocalização de
    IP (`cidade_do_ip`/`ip-api.com` no Mesk) — esse dado fazia sentido numa capa pública
    voltada a visitantes externos; o dashboard do cade-monitor é autenticado, para a própria
    equipe, onde esse dado não tem propósito.
  - **Fora de escopo, delegado à feature de Agenda/Prazos**: os helpers de formatação de data por
    extenso e contagem de prazo (`data_por_extenso`, `dias_ate`, `prazo_selo`/`prazo_frase`) do
    `hub.py` original pertencem, em espírito, à calculadora de prazos (`calendario.py`), que será
    portada como sua própria feature — evita duplicar essa lógica aqui.
- O dashboard já existente (`apps/dashboard/`, autenticado) é o único lugar onde o cartão de
  sessão aparece nesta versão — não há capa pública nova.
- `www.gov.br/cade` (calendário e pautas de sessão) é tratado como página pública do CADE já em
  escopo do Princípio II, mesmo hospedada no domínio compartilhado `gov.br` (é o espaço oficial do
  próprio CADE nesse portal, não uma fonte de terceiro) — mesmo racional já aplicado a
  `cdn.cade.gov.br`. Ver plan.md, Constitution Check.
