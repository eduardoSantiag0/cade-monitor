# Feature Specification: Precedentes — dossiê de due diligence (fundação)

**Feature Branch**: `013-precedentes-due-diligence`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "Precedentes: due diligence de atos de concentração — dossiê e busca de precedentes para caso de fusão/aquisição em análise no CADE."

**Escopo desta spec**: esta é a **primeira de uma série de specs** dentro da iniciativa "Precedentes" (confirmado com o dono do projeto: o volume — 16 tabelas, pipeline de 8 etapas — e o número de fontes/decisões novas tornam uma spec monolítica inadequada, Princípios III/VIII). Esta spec cobre só a **fundação**: o modelo de dados de um caso de due diligence (empresas, fatos, evidências) e a disciplina de revisão humana com histórico versionado — o princípio central "fato ≠ análise, tudo com evidência anexada". Dados são inseridos manualmente pelo advogado nesta versão; nenhuma fonte externa nova é consultada. Pesquisa societária automática (SEC/EDGAR, CVM, Receita Federal), busca de jurisprudência (Solr do CADE), extração de documentos e relatório final ficam para specs seguintes, cada uma com suas próprias decisões de escopo/constituição.

**Decisão já tomada com o dono do projeto**: **sem IA nesta versão** (nem nas futuras specs de extração, por ora) — nenhuma chamada a provedor de IA em nenhum ponto desta funcionalidade. Campos que dependeriam de extração por IA ficam de fora ou exigem entrada manual do advogado; nada é adivinhado.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Abrir um caso e registrar as partes (Priority: P1)

Um advogado, ao começar a due diligence de uma operação em análise no CADE, cria um caso com um
título e cliente, e registra as empresas envolvidas (partes da operação), cada uma com o papel que
exerce (requerente, parte identificada, etc.) e os dados básicos que já conhece (razão social,
CNPJ, país). O caso fica visível numa lista, com um resumo de quantas empresas e fatos já tem.

**Why this priority**: é o ponto de partida de qualquer due diligence — sem um caso e suas partes,
não há nada para as próximas histórias trabalharem em cima.

**Independent Test**: criar um caso com 2 empresas (uma requerente, uma parte identificada) e
confirmar que ambas aparecem na página do caso com seus dados e papéis corretos.

**Acceptance Scenarios**:

1. **Given** um advogado autenticado, **When** cria um caso com título e cliente, **Then** o caso
   aparece na lista de casos, visível só para quem tem acesso ao painel (mesma exigência de
   autenticação do resto do sistema).
2. **Given** um caso já criado, **When** o advogado adiciona uma empresa com papel "requerente",
   razão social e CNPJ, **Then** a empresa aparece na página do caso com esses dados.
3. **Given** um caso com uma empresa já cadastrada, **When** o advogado edita o papel ou os dados
   básicos dessa empresa, **Then** os dados atualizados aparecem, sem duplicar a empresa.
4. **Given** um caso com empresas cadastradas, **When** o advogado remove uma empresa adicionada
   por engano, **Then** ela some da página do caso (e de tudo que dependia só dela).

---

### User Story 2 - Registrar fatos com evidência, cada um com um status claro (Priority: P1)

Para cada empresa do caso, o advogado registra fatos (ex.: faturamento, controladora, atividade
principal) — cada fato tem um valor, uma fonte (de onde veio: URL, documento, ou "informação do
cliente") e, quando houver, uma citação/trecho de evidência. Todo fato carrega um status que deixa
claro sua confiabilidade: confirmado (com evidência clara), a confirmar com o cliente (encontrado
mas precisa de validação), a solicitar ao cliente (ainda não se sabe), ou não localizado (buscado e
genuinamente ausente). A página do caso mostra, de forma legível, quais fatos já estão confirmados
e quais ainda precisam de atenção.

**Why this priority**: é o "o que sabemos" do due diligence — sem fatos com evidência e status
claro, o caso é só uma lista de nomes de empresa, sem nenhum conteúdo de due diligence de verdade.

**Independent Test**: registrar 3 fatos para uma mesma empresa com os 4 status diferentes e
confirmar que a página do caso os agrupa/destaca de forma que dá pra saber, sem esforço, quais
ainda precisam de atenção.

**Acceptance Scenarios**:

1. **Given** uma empresa do caso, **When** o advogado registra um fato com valor, fonte e status
   "confirmado", **Then** o fato aparece associado a essa empresa com esse status.
2. **Given** um fato registrado com status "a solicitar ao cliente", **When** a página do caso é
   aberta, **Then** esse fato aparece destacado como pendência (distinto visualmente de um fato
   confirmado).
3. **Given** um fato com uma citação de evidência (trecho de texto + fonte), **When** o fato é
   exibido, **Then** a citação e a fonte aparecem junto do valor — nunca um valor sem se saber de
   onde veio.
4. **Given** um fato sem nenhuma fonte informada, **When** o advogado tenta salvá-lo com status
   "confirmado", **Then** o sistema não aceita — "confirmado sem citação não é confirmado".

---

### User Story 3 - Corrigir um fato sem nunca perder o histórico (Priority: P2)

Quando uma informação registrada precisa mudar (o advogado descobriu que o valor estava errado, ou
uma nova informação contradiz a anterior), o sistema nunca sobrescreve o valor antigo: grava uma
nova versão do fato, mantendo a anterior visível no histórico, com quem mudou, quando, e por quê.
Um fato já confirmado nunca desaparece silenciosamente — só é substituído por uma ação explícita e
registrada do advogado.

**Why this priority**: é o que torna o due diligence auditável e confiável ao longo do tempo — sem
isso, um erro de digitação ou uma correção apressada pode apagar informação sem deixar rastro, o
oposto do que um documento jurídico exige.

**Independent Test**: registrar um fato, corrigi-lo duas vezes seguidas com motivos diferentes, e
confirmar que as 3 versões (original + 2 correções) ficam todas visíveis no histórico do fato, na
ordem certa, cada uma com seu motivo.

**Acceptance Scenarios**:

1. **Given** um fato já registrado, **When** o advogado o corrige (novo valor + motivo
   obrigatório), **Then** uma nova versão é criada, a versão anterior fica marcada como não-atual
   mas continua visível no histórico, e o motivo da correção fica registrado.
2. **Given** um fato com 3 versões no histórico, **When** o advogado consulta o histórico desse
   fato, **Then** vê as 3 versões em ordem cronológica, cada uma com valor, quem alterou, quando, e
   o motivo (quando for uma correção).
3. **Given** um fato, **When** o advogado tenta corrigi-lo sem informar um motivo, **Then** o
   sistema não aceita a correção sem motivo.

---

### User Story 4 - Registrar uma análise separada dos fatos que a sustentam (Priority: P2)

O advogado pode registrar uma anotação de análise (uma hipótese, uma conclusão, uma observação
interpretativa) associada explicitamente aos fatos em que ela se baseia — nunca misturada com os
fatos em si. A página do caso mostra fatos e análises em seções/destaques visualmente distintos, de
forma que ninguém confunda "o que está documentado" com "o que o advogado concluiu a partir disso".

**Why this priority**: é o princípio central desta iniciativa ("fato ≠ análise") aplicado desde o início,
mesmo antes de haver pesquisa automatizada — evita que o hábito de misturar fato e interpretação se
instale desde a v1.

**Independent Test**: registrar 2 fatos de uma empresa e uma análise que cita os dois, e confirmar
que a análise aparece claramente marcada como análise (não como um terceiro fato), com links/
referências visíveis para os 2 fatos que a sustentam.

**Acceptance Scenarios**:

1. **Given** dois fatos já registrados no caso, **When** o advogado registra uma análise citando
   os dois como base, **Then** a análise aparece na página do caso, visualmente distinta de um
   fato, com uma referência aos fatos que a sustentam.
2. **Given** uma análise registrada, **When** um dos fatos que a sustentam é corrigido (História
   3), **Then** a análise continua existindo e ainda referenciando esse fato (pela sua identidade,
   não pelo valor antigo) — não é apagada nem "perde" a referência por causa da correção.
3. **Given** a página do caso, **When** aberta, **Then** a contagem de fatos e a contagem de
   análises aparecem separadas — nunca somadas como se fossem a mesma coisa.

---

### Edge Cases

- Duas empresas do mesmo caso com o mesmo CNPJ cadastradas por engano: o sistema não impede (podem
  ser legitimamente a mesma empresa citada com papéis diferentes), mas não deduplica
  automaticamente — fica a critério do advogado.
- Fato registrado sem nenhum valor preenchido: não é aceito — um fato sem valor não é um fato, é a
  ausência de um.
- Correção que muda o status de "confirmado" para "não localizado": permitida (o advogado pode
  perceber que uma evidência anterior não era, na verdade, conclusiva) — vira uma nova versão como
  qualquer outra correção, com o motivo explicando.
- Remover uma empresa que tem fatos e análises associados: os fatos/análises dela são removidos
  junto (não ficam órfãos) — o advogado é avisado do que será removido antes de confirmar.
- Caso sem nenhuma empresa ainda: a página do caso existe e mostra um estado vazio claro, orientando
  o próximo passo (adicionar uma empresa), nunca um erro.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST permitir que um usuário autenticado crie um caso de due diligence com
  título e cliente, visível numa lista de casos.
- **FR-002**: O sistema MUST permitir registrar, editar e remover empresas (partes) dentro de um
  caso, cada uma com papel (ex.: requerente, parte identificada), razão social, CNPJ (opcional) e
  país.
- **FR-003**: O sistema MUST permitir registrar um fato associado a uma empresa do caso, com valor,
  fonte (URL, documento ou "informação do cliente"), status (confirmado / a confirmar com o cliente
  / a solicitar ao cliente / não localizado) e, opcionalmente, uma citação/trecho de evidência.
- **FR-004**: O sistema MUST NOT aceitar um fato com status "confirmado" sem uma fonte informada.
- **FR-005**: O sistema MUST NOT aceitar um fato sem valor preenchido.
- **FR-006**: O sistema MUST tratar toda correção de um fato como a criação de uma nova versão,
  nunca como uma edição que sobrescreve o valor anterior — a versão anterior MUST permanecer
  consultável no histórico do fato.
- **FR-007**: O sistema MUST exigir um motivo (texto) para toda correção de um fato já existente.
- **FR-008**: O sistema MUST registrar, para cada versão de um fato, quem fez a alteração e quando.
- **FR-009**: O sistema MUST permitir consultar o histórico completo de versões de qualquer fato,
  em ordem cronológica.
- **FR-010**: O sistema MUST permitir registrar uma análise (nota interpretativa) associada
  explicitamente a um ou mais fatos existentes do caso, MUST manter análises numa estrutura
  separada dos fatos (nunca misturadas na mesma listagem/contagem), e MUST manter a referência aos
  fatos-base íntegra mesmo quando um desses fatos ganha uma nova versão (FR-006).
- **FR-011**: O sistema MUST exibir, na página do caso, fatos e análises com destaque visual
  distinto, de forma que um usuário não técnico consiga diferenciar os dois à primeira vista.
- **FR-012**: O sistema MUST remover, ao remover uma empresa do caso, os fatos e análises que
  dependem só dela, avisando o usuário do que será removido antes de confirmar.
- **FR-013**: O sistema MUST exigir autenticação para criar, ver, editar ou remover qualquer dado
  de um caso — mesma exigência já aplicada ao resto do painel.

### Key Entities *(include if feature involves data)*

- **Caso (due diligence)**: um dossiê de uma operação em análise no CADE — título, cliente, quem
  criou, quando.
- **Empresa (parte)**: uma empresa envolvida num caso — papel na operação, razão social, CNPJ,
  país.
- **Fato**: uma informação sobre uma empresa do caso, com valor, fonte, status de confiabilidade e
  histórico de versões (cada versão com quem/quando/motivo).
- **Evidência**: a citação/trecho que sustenta um fato, ligada à fonte de onde veio.
- **Análise**: uma nota interpretativa do advogado, associada a um ou mais fatos-base, mantida
  estruturalmente separada dos fatos.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Em 100% dos casos de teste automatizado, um fato com status "confirmado" e sem fonte
  é rejeitado pelo sistema (FR-004 nunca falha silenciosamente).
- **SC-002**: Em 100% dos casos de teste automatizado, corrigir um fato preserva a versão anterior
  consultável no histórico — nenhuma correção jamais apaga a versão anterior.
- **SC-003**: Um usuário não técnico, olhando a página de um caso com fatos e análises misturados
  na criação, consegue identificar corretamente quais itens são fatos e quais são análises sem
  ajuda (validável por teste manual de legibilidade, mesmo critério já usado na feature 009).
- **SC-004**: Em teste automatizado, remover uma empresa com fatos e análises associados não deixa
  nenhum registro órfão (fato/análise sem empresa/fato-base válido) no banco.

## Assumptions

- **Sem IA nesta versão** (decisão confirmada com o dono do projeto) — e, adicionalmente, nenhuma
  fonte externa nova é consultada nesta spec: toda entrada é manual. Pesquisa societária automática
  (SEC/EDGAR, CVM, Receita Federal — exige emenda de constituição própria, fontes novas) e busca de
  jurisprudência no CADE (Solr, já em escopo pela emenda v2.2.0) ficam para specs seguintes desta
  mesma iniciativa "Precedentes".
- Extração automática de dados de PDFs de pareceres/votos (o que dependeria de IA) fica
  fora de escopo desta spec inteira — quando uma spec futura tratar de extração de documentos, será
  só por regra/regex (nomes de campo, formato de data, rótulos fixos), nunca por IA, seguindo a
  decisão já tomada.
- O "papel" da empresa no caso (requerente, parte identificada) usa uma lista fixa e pequena de
  valores — suficiente para due diligence de atos de concentração, sem grafo de relações
  societárias/grupo econômico automático (isso, quando/se vier, é melhoria futura).
- Um caso não precisa estar ligado a um `MonitoredProcess` já monitorado neste sistema — devido
  diligence pode começar antes de haver um processo público no SEI para acompanhar.
- Relatório final, cofre/base de conhecimento (cache de documentos entre casos), pesquisa
  societária e busca de jurisprudência ficam fora desta spec — são specs seguintes da mesma
  iniciativa, cada uma com seu próprio spec.md.
