# Feature Specification: Agenda e prazos de AC sumário

**Feature Branch**: `011-agenda-prazos-ac`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "Agenda / Prazos / Lembretes / Calendário: calendário oficial de expediente do CADE (`calendario.py`), linha do tempo de prazos de um AC sumário a partir dos documentos (`prazos.py`), convites de calendário que se atualizam se a previsão mudar (`agenda.py`)." Porte do comportamento dos módulos homônimos do projeto irmão "Mesk". Decisões de escopo já tomadas em conversa com o dono do projeto (ver Assumptions): lembretes = só convite de calendário (sem push proativo "N dias antes"); convite só para os prazos "do escritório" (análise da SG e certidão final); auto-encerramento portado como no Mesk, **incluindo o apagamento irreversível** do processo/assinantes/documentos 10 dias após a certidão sem nova movimentação.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver a linha do tempo de prazos de um AC sumário (Priority: P1)

Um usuário abre a página de um processo monitorado que é um Ato de Concentração Sumário e vê,
além do que já existe hoje, uma linha do tempo com os prazos calculados a partir dos documentos
já extraídos do SEI: prazo de análise da Superintendência-Geral, prazo de terceiro interessado,
prazo de recurso/avocação, e a certidão de trânsito em julgado (real, quando já emitida, ou
prevista, quando ainda não). Os prazos são calculados pelo calendário oficial de expediente do
CADE (dias úteis reais, não dias corridos), mantido atualizado em segundo plano. Processos que
não são AC sumário não mostram essa linha do tempo.

**Why this priority**: É o valor central da feature — sem isso não há prazo calculado algum. As
Histórias 2 e 3 dependem desta base (convite de calendário e auto-encerramento leem a mesma linha
do tempo).

**Independent Test**: com fixtures de documentos de um AC sumário representando diferentes
estágios (só notificação, notificação + edital + publicação, já com despacho de aprovação, já com
certidão) e um calendário oficial fixo, confirmar que a linha do tempo mostra os prazos corretos
para cada estágio, incluindo o prazo de análise desaparecendo assim que a aprovação é encontrada.

**Acceptance Scenarios**:

1. **Given** um processo classificado como Ato de Concentração Sumário com um documento de
   notificação protocolado em uma data conhecida, **When** a linha do tempo é calculada,
   **Then** o prazo de análise da SG aparece como 30 dias corridos a partir do primeiro dia útil
   do CADE após a data de protocolo, ajustado para o próximo dia útil se cair em dia não útil.
2. **Given** o mesmo processo, agora com um edital publicado no DOU, **When** a linha do tempo é
   recalculada, **Then** o prazo de terceiro interessado aparece como 15 dias a partir da
   publicação do edital, calculado pelo mesmo calendário oficial.
3. **Given** o processo já tem um despacho de aprovação da SG (não um despacho decisório de
   acesso restrito, nem um despacho ordinatório) publicado no DOU, **When** a linha do tempo é
   recalculada, **Then** o prazo de análise da SG não aparece mais (foi cumprido), e o prazo de
   recurso/avocação aparece como 15 dias a partir dessa publicação.
4. **Given** o processo ainda não tem certidão de trânsito em julgado, **When** a linha do tempo é
   calculada, **Then** a certidão final aparece como uma previsão (primeiro dia útil após o
   vencimento do prazo de recurso), marcada como estimativa, não como confirmada.
5. **Given** o processo já tem uma certidão de trânsito em julgado real, **When** a linha do tempo
   é calculada, **Then** a certidão final aparece com a data real do documento, não mais como
   estimativa.
6. **Given** um processo que não é Ato de Concentração Sumário (ex.: Processo Administrativo
   Ordinário), **When** a página do processo é aberta, **Then** nenhuma linha do tempo de prazos
   aparece.
7. **Given** o calendário oficial do ano em questão ainda não foi confirmado (ato oficial ainda
   não publicado ou não localizado), **When** a linha do tempo é calculada, **Then** o sistema usa
   a melhor informação disponível (ou não mostra prazo algum, se não houver nenhuma), nunca
   trava nem mostra erro.

---

### User Story 2 - Receber convite de calendário para os prazos do escritório (Priority: P2)

Um assinante do processo (com a mesma preferência de canal já usada para notificações de mudança)
recebe, por e-mail, um convite de calendário (arquivo `.ics`) quando o prazo de análise da SG é
identificado pela primeira vez, e outro quando a certidão final (real ou prevista) é identificada
— só esses dois tipos de prazo geram convite; terceiro interessado e recurso/avocação ficam só na
linha do tempo (História 1), por serem prazos do CADE/de terceiros, não do escritório. Se a
previsão de um prazo já convidado mudar (ex.: a certidão prevista passa a ter uma data diferente,
ou o prazo de análise é cumprido antes do esperado), um convite atualizado é enviado, substituindo
o anterior no calendário do assinante (mesmo compromisso, não um novo). Quando um prazo deixa de
existir (ex.: prazo de análise cumprido pela aprovação), o convite correspondente é cancelado.

**Why this priority**: Depende da História 1 já estar calculando os prazos corretamente; é a
entrega que efetivamente chega ao dia a dia do assinante (calendário pessoal), mas sem valor sem
a base da História 1.

**Independent Test**: com uma linha do tempo fixa (fixture) passando por: prazo de análise
identificado → prazo de análise cumprido (aprovação) → certidão prevista → certidão real com data
diferente da prevista, confirmar a sequência de convites (REQUEST, CANCEL, REQUEST, REQUEST com
sequência incrementada) enviados a cada mudança, sem repetir convite para uma previsão que não
mudou.

**Acceptance Scenarios**:

1. **Given** o prazo de análise da SG é identificado pela primeira vez para um processo,
   **When** o próximo ciclo de verificação roda, **Then** o assinante do processo (com e-mail
   habilitado) recebe um e-mail com um convite de calendário anexado para esse prazo.
2. **Given** um convite de prazo de análise já foi enviado e nada mudou, **When** o próximo ciclo
   roda, **Then** nenhum e-mail novo é enviado (idempotência).
3. **Given** o prazo de análise é cumprido (aprovação encontrada) depois de um convite já ter sido
   enviado, **When** o próximo ciclo roda, **Then** o assinante recebe um convite de cancelamento
   do compromisso de análise.
4. **Given** a certidão final estava prevista para uma data e passa a ser real com uma data
   diferente, **When** o próximo ciclo roda, **Then** o assinante recebe um convite atualizado
   (mesmo compromisso, nova data) para a certidão final.
5. **Given** um assinante do processo tem o e-mail desabilitado, **When** qualquer prazo com
   convite é identificado/atualizado, **Then** esse assinante não recebe nenhum convite.

---

### User Story 3 - Auto-encerramento do processo sem movimentação após a certidão (Priority: P3)

Quando um processo tem uma certidão de trânsito em julgado (real, com confiança alta de que é de
fato a certidão certa) e passa 10 dias sem nenhuma nova movimentação detectada, o processo — e
tudo o que está ligado só a ele (assinaturas e documentos) — é apagado do sistema. Qualquer nova
movimentação detectada antes desses 10 dias reinicia a contagem. Este comportamento é irreversível
e só roda com verificações de segurança explícitas: nunca apaga se a última verificação do
processo teve erro, se a última verificação é mais antiga que 2 dias (dado potencialmente
desatualizado), ou se a confiança de que o documento é realmente a certidão de trânsito em
julgado for baixa.

**Why this priority**: É a prioridade mais baixa das três por ser a de maior risco (ação
irreversível) e por só fazer sentido depois que a História 1 já identifica a certidão de forma
confiável — nunca deve rodar antes disso estar maduro.

**Independent Test**: com fixtures de processo com certidão real há mais de 10 dias sem
movimentação (deve apagar), certidão há menos de 10 dias (não deve apagar), certidão + nova
movimentação depois dela (contagem reiniciada, não deve apagar), e os três casos de guarda de
segurança (erro na última verificação, verificação desatualizada, confiança baixa na certidão —
nenhum deve apagar mesmo com 10+ dias), confirmar o comportamento esperado em cada um.

**Acceptance Scenarios**:

1. **Given** um processo AC sumário com certidão de trânsito em julgado (confiança alta) datada
   há 11 dias, sem nenhuma movimentação nova desde então, e a última verificação do processo bem
   sucedida e recente, **When** o ciclo de verificação de auto-encerramento roda, **Then** o
   processo, suas assinaturas e seus documentos são apagados do sistema.
2. **Given** o mesmo cenário, mas a certidão é de há 5 dias, **When** o ciclo roda, **Then** o
   processo NÃO é apagado (ainda dentro da janela dos 10 dias).
3. **Given** o processo tem certidão há 15 dias, mas uma nova movimentação foi detectada há 3
   dias (depois da certidão), **When** o ciclo roda, **Then** o processo NÃO é apagado (a
   contagem reinicia a partir da movimentação mais recente).
4. **Given** o processo tem certidão há 15 dias sem movimentação nova, mas a última verificação
   do processo terminou em erro, **When** o ciclo roda, **Then** o processo NÃO é apagado.
5. **Given** o mesmo cenário, mas a última verificação bem-sucedida tem mais de 2 dias,
   **When** o ciclo roda, **Then** o processo NÃO é apagado.
6. **Given** o mesmo cenário, mas o documento identificado como certidão tem confiança baixa de
   ser de fato a certidão de trânsito em julgado certa, **When** o ciclo roda, **Then** o
   processo NÃO é apagado.

---

### Edge Cases

- Documento de aprovação (despacho da SG) existe mas nenhuma publicação correspondente no DOU
  aparece dentro da janela de 20 dias: o prazo de recurso/avocação não é calculado ainda (falta a
  data de publicação que o dispara), a linha do tempo mostra isso como pendente, não como erro.
- Mais de um documento de notificação no processo (ex.: uma complementação): a linha do tempo usa
  o primeiro documento de notificação real, ignorando recibos/emendas/complementações/respostas,
  como o filtro já determina.
- Ano do calendário oficial ainda sem ato publicado (ex.: início de ano, antes da Portaria sair):
  o sistema não calcula (ou calcula com incerteza sinalizada) os prazos que caem nesse ano,
  nunca usando uma suposição não confirmada como se fosse certeza.
- Assinante com o processo pausado (`ProcessSubscription.paused`): não recebe convite de
  calendário, mesmo com prazo novo/atualizado (mesma regra já aplicada às notificações de
  mudança).
- Processo apagado por auto-encerramento (História 3) enquanto tinha um convite de calendário
  pendente de cancelamento: o cancelamento é enviado antes (ou como parte) do apagamento — o
  assinante nunca fica com um compromisso "fantasma" no calendário sem explicação.

## Requirements *(mandatory)*

### Functional Requirements

**Calendário oficial (base para as três histórias)**

- **FR-001**: O sistema MUST manter, em segundo plano, um calendário de dias úteis de expediente
  do CADE por ano, obtido a partir do ato oficial (Portaria) publicado no Diário Oficial da União
  que fixa os feriados nacionais e pontos facultativos da administração pública federal.
- **FR-002**: O sistema MUST validar o ato encontrado antes de aceitá-lo como calendário oficial
  do ano (é uma Portaria, do órgão competente, publicada na Seção 1 do DOU, não revogada, com um
  número mínimo de datas e nenhuma fora do ano-alvo) — um ato que não passa nessa validação MUST
  NOT ser usado.
- **FR-003**: O sistema MUST atualizar o calendário de cada ano com cadência diária durante a
  janela em que o ato costuma ser publicado (novembro do ano anterior a janeiro do ano-alvo) até
  ficar confirmado, e com cadência de pelo menos 30 dias depois de confirmado.
- **FR-004**: O sistema MUST calcular um prazo a partir de uma data-evento e uma quantidade de
  dias da seguinte forma: o prazo começa a contar no primeiro dia útil do CADE estritamente após
  a data-evento; o vencimento preliminar é esse início mais (quantidade de dias − 1) dias
  corridos; o vencimento final é o preliminar, ou o próximo dia útil do CADE se o preliminar cair
  em dia não útil.

**Linha do tempo de prazos (User Story 1)**

- **FR-005**: O sistema MUST considerar um processo elegível para cálculo de prazos apenas quando
  sua classificação (extraída do próprio processo) for Ato de Concentração Sumário — MUST NOT
  calcular prazos para classificações que apenas soem parecidas (ordinário, apuração, consulta,
  recurso, etc.).
- **FR-006**: O sistema MUST identificar, a partir dos documentos já extraídos do processo: o
  documento de notificação (protocolo de abertura), o edital, a publicação da notificação/edital
  no DOU, o despacho de aprovação da Superintendência-Geral (distinto de despacho decisório de
  acesso restrito e de despacho ordinatório), e a certidão de trânsito em julgado — cada
  identificação MUST ter um grau de confiança associado, nunca tratada como absoluta quando o
  padrão encontrado for ambíguo.
- **FR-007**: O sistema MUST calcular o prazo de análise da Superintendência-Geral como 30 dias
  corridos a partir da data de protocolo (registro) do documento de notificação, pela fórmula de
  FR-004, e MUST parar de exibi-lo assim que o despacho de aprovação for identificado.
- **FR-008**: O sistema MUST calcular o prazo de terceiro interessado como 15 dias a partir da
  data de publicação do edital no DOU, pela fórmula de FR-004.
- **FR-009**: O sistema MUST calcular o prazo de recurso/avocação como 15 dias a partir da data de
  publicação do despacho de aprovação no DOU, pela fórmula de FR-004.
- **FR-010**: O sistema MUST exibir a certidão de trânsito em julgado com a data real do
  documento quando ele existir no processo, ou, quando não existir, como uma previsão (primeiro
  dia útil do CADE após o vencimento do prazo de recurso/avocação) claramente marcada como
  estimativa.
- **FR-011**: O sistema MUST NOT travar nem exibir erro visível quando o calendário oficial do ano
  necessário ainda não estiver confirmado — MUST tratar prazos que dependam desse ano como
  indisponíveis/pendentes em vez de usar uma data não confirmada como certeza.

**Convites de calendário (User Story 2)**

- **FR-012**: O sistema MUST gerar um convite de calendário (arquivo `.ics`, gerado sem
  dependência nova) para o prazo de análise da SG e para a certidão final (real ou prevista), e
  MUST NOT gerar convite para o prazo de terceiro interessado nem para o de recurso/avocação.
- **FR-013**: O sistema MUST enviar o convite por e-mail a cada assinante do processo com e-mail
  habilitado e não pausado, reaproveitando a mesma preferência de canal já usada para notificações
  de mudança do processo (`ProcessSubscription`).
- **FR-014**: O sistema MUST NOT reenviar um convite cuja data prevista não mudou desde o último
  envio (idempotência).
- **FR-015**: O sistema MUST enviar um convite atualizado (mesmo identificador de compromisso,
  sequência incrementada) quando a data de um prazo já convidado mudar.
- **FR-016**: O sistema MUST enviar um convite de cancelamento quando um prazo já convidado deixar
  de existir (ex.: prazo de análise cumprido pela aprovação).

**Auto-encerramento (User Story 3)**

- **FR-017**: O sistema MUST apagar um processo (e suas assinaturas e documentos vinculados)
  quando, simultaneamente: (a) existir uma certidão de trânsito em julgado identificada com
  confiança alta; (b) não houver nenhuma movimentação nova detectada no processo há pelo menos 10
  dias corridos contados a partir da certidão ou de qualquer movimentação posterior a ela, o que
  for mais recente; (c) a última verificação do processo tiver terminado sem erro; (d) essa
  última verificação bem-sucedida tiver no máximo 2 dias.
- **FR-018**: O sistema MUST NOT apagar um processo quando qualquer uma das condições de FR-017
  não for satisfeita, mesmo que as demais estejam.
- **FR-019**: O sistema MUST enviar o cancelamento de qualquer convite de calendário pendente
  desse processo antes ou como parte do apagamento (FR-016), nunca deixando um compromisso sem
  explicação no calendário do assinante.
- **FR-020**: Esta é uma ação destrutiva e irreversível — o sistema MUST registrar em log,
  antes de executar, os critérios que levaram à decisão (datas, confiança, processo), para
  permitir auditoria posterior.

### Key Entities *(include if feature involves data)*

- **Calendário oficial do ano**: ano, status (não confirmado/confirmado/com conflito), o ato
  oficial que o define (quando localizado), lista de dias não úteis (feriados/pontos
  facultativos) daquele ano.
- **Linha do tempo de prazos**: para um processo elegível, o conjunto de prazos calculados (cada
  um com tipo, data de vencimento, se é real ou estimado, e a confiança da identificação do
  documento que o originou) — recalculada a cada verificação, não persistida como histórico
  próprio (deriva sempre dos documentos + calendário atuais).
- **Convite de calendário enviado**: por processo e tipo de prazo, o identificador do compromisso,
  a data já enviada e o número de sequência — usado para saber se precisa reenviar, atualizar ou
  cancelar.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Para qualquer AC sumário com documentos completos (notificação, edital, publicação,
  aprovação, certidão) em teste automatizado, os quatro prazos calculados batem exatamente com a
  fórmula de FR-004 aplicada ao calendário oficial de teste, em 100% dos cenários de fixture.
- **SC-002**: Nenhum convite de calendário duplicado (mesmo tipo de prazo, mesma data, mesmo
  processo) é enviado ao mesmo assinante, verificável pelo registro de convites já enviados.
- **SC-003**: Em nenhum cenário de teste (incluindo calendário oficial não confirmado, documentos
  incompletos, ou ausência de qualquer prazo) o cálculo da linha do tempo ou o envio de convite
  lança exceção ou expõe erro ao usuário.
- **SC-004**: O auto-encerramento nunca dispara em teste automatizado fora exatamente das
  condições de FR-017 — cada uma das quatro condições, testada isoladamente como ausente, impede
  o apagamento (SC verificável pelos cenários de guarda de segurança).

## Assumptions

- **Lembretes = só convite de calendário** (decisão confirmada em conversa): sem notificação
  proativa "N dias antes" — quem lembra o assinante é o próprio aplicativo de calendário dele, a
  partir do `.ics` recebido. Se o dono do projeto quiser lembrete proativo no futuro, é uma
  extensão separada, fora desta spec.
- **Só os prazos "do escritório" (análise da SG, certidão final) geram convite** (decisão
  confirmada em conversa) — terceiro interessado e recurso/avocação são prazos do CADE/de
  terceiros, informativos na linha do tempo, sem convite de calendário.
- **Auto-encerramento portado como no Mesk, apagamento real e irreversível** (decisão confirmada
  em conversa, com plena ciência de que é destrutivo) — mantendo as mesmas quatro guardas de
  segurança do comportamento original (FR-017/FR-018), para minimizar o risco de apagar processo
  ativo por engano.
- **Fonte da camada de suspensões específicas do CADE (além do calendário nacional de feriados)
  fica fora do escopo desta versão**: o Mesk também consulta um endpoint de busca do gov.br
  (domínio diferente de `in.gov.br`/`gov.br/cade`, já em escopo) para comunicados avulsos de
  suspensão de prazo específicos do CADE; portar essa camada exigiria uma nova avaliação de escopo
  do Princípio II. O calendário nacional de feriados (já em escopo via `in.gov.br`, emenda v2.2.0)
  é suficiente para a maioria dos casos e cobre o v1 — a camada de comunicados avulsos fica
  registrada como melhoria futura.
- **Classificação do processo** (Ato de Concentração Sumário) é extraída do texto já coletado do
  processo (`MonitoredProcess.last_text`) por um padrão a ser confirmado/ajustado durante a
  implementação, seguindo o mesmo processo de validação ao vivo das features anteriores.
- Reaproveita `ProcessSubscription` (já existente) para saber quem recebe convite — sem lista de
  assinantes própria para esta feature, diferente do que a feature 009 precisou fazer para o
  digest do DOU (que não é por processo).
