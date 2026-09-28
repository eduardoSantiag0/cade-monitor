# Feature Specification: Digest diário do DOU

**Feature Branch**: `009-digest-diario-dou`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "Digest diário do DOU (Diário Oficial da União) com publicações do CADE, para assinantes por e-mail." (ver histórico completo da sessão para o detalhamento das três histórias de usuário, limites de escopo e critérios de sucesso).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Digest diário das publicações do CADE no DOU (Priority: P1)

Um assinante cadastrado para o digest do DOU recebe, uma vez por dia, um e-mail em português
resumindo as publicações do CADE que saíram no Diário Oficial da União naquele dia: editais
(avisos públicos) e despachos (decisões/atos). Títulos de caso e nomes de partes aparecem em
negrito; despachos muito longos vêm resumidos (início + conclusão); qualquer termo que o
assinante monitora (pessoa, empresa, palavra-chave) aparece destacado em amarelo no e-mail.
Pautas/atas de sessão do CADE do dia, quando houver, aparecem num rodapé do e-mail com link para
o DOU. Em dias sem nenhuma publicação do CADE, o assinante ainda recebe um e-mail curto avisando
que não houve publicações naquele dia — o sistema nunca fica em silêncio.

**Why this priority**: É o valor central da feature — sem isso não há digest algum. As histórias
2 e 3 (antecipação/confirmação) dependem do mesmo motor de formatação e do mesmo cadastro de
assinante, mas são incrementos sobre esta base.

**Independent Test**: Pode ser testado sozinho: com fixtures da Resenha do CADE (e, separadamente,
fixtures da listagem do in.gov.br) representando um dia com publicações, um dia sem nenhuma, e um
dia com termo monitorado presente/ausente, o teste verifica o conteúdo e formatação do e-mail
gerado e que exatamente um e-mail por assinante por dia é enviado.

**Acceptance Scenarios**:

1. **Given** a Resenha do CADE do dia está disponível e contém 1 edital e 2 despachos citando o
   caso "Ato de Concentração nº 08700.001234/2026-11", **When** a janela diária de busca do
   digest é processada, **Then** cada assinante ativo do digest recebe um e-mail com os 3 itens,
   título do caso em negrito, nomes de partes em negrito, e despacho longo truncado
   (início + "(...)" + conclusão) quando aplicável.
2. **Given** um assinante tem o termo monitorado "Empresa XYZ" cadastrado e um dos itens do dia
   cita esse termo, **When** o e-mail desse assinante é montado, **Then** o bloco inteiro que
   contém o termo aparece com destaque (fundo amarelo), enquanto o e-mail de outro assinante sem
   esse termo cadastrado mostra o mesmo item sem destaque.
3. **Given** a Resenha do dia não fica disponível dentro da janela de busca, **When** o sistema
   tenta a fonte alternativa (listagem pública do DOU em in.gov.br, filtrada para itens do CADE)
   e ela retorna itens, **Then** o digest é montado a partir dessa fonte alternativa e enviado
   normalmente, com o mesmo formato.
4. **Given** nenhuma das duas fontes retorna nenhuma publicação do CADE no dia, **When** a janela
   de busca se encerra, **Then** todo assinante ativo recebe um e-mail avisando que não houve
   publicações do CADE no DOU daquele dia.
5. **Given** o digest de um assinante já foi enviado hoje, **When** o sistema roda novamente
   dentro da mesma janela (ex.: nova tentativa após falha parcial), **Then** nenhum segundo
   e-mail de digest é enviado a esse assinante no mesmo dia.

---

### User Story 2 - Antecipação da véspera (Priority: P2)

Um assinante que optou pelo recurso de antecipação recebe, no fim da tarde/início da noite (em
horário configurável, com um padrão razoável), um e-mail antecipando — a partir do boletim/
resenha do SEI do próprio dia — quais andamentos processuais devem sair no DOU do dia seguinte,
no mesmo formato de negrito/destaque da História 1. Se, depois desse envio, a apuração do SEI
identificar itens novos antes de um horário-limite da noite, um e-mail complementar é enviado
contendo só os itens novos (sem repetir o que já foi antecipado). Quando não há nada a antecipar,
o assinante recebe um e-mail curto avisando isso.

**Why this priority**: Depende do motor de formatação da História 1 mas é opcional e configurável
por assinante — entrega valor incremental (previsibilidade) sem ser pré-requisito do digest
básico.

**Independent Test**: Testável isoladamente com fixtures do boletim do SEI representando: itens
presentes no fim da tarde; itens que só aparecem numa checagem posterior da noite (deve gerar
e-mail complementar); e um dia sem nenhum item (deve gerar aviso curto). Verifica-se o conteúdo
do e-mail e que o e-mail complementar nunca repete item já antecipado.

**Acceptance Scenarios**:

1. **Given** um assinante habilitou a antecipação com horário configurado, **When** o boletim do
   SEI do dia traz 2 andamentos relevantes até esse horário, **Then** o assinante recebe, no
   horário configurado, um e-mail de antecipação com os 2 andamentos formatados.
2. **Given** o e-mail de antecipação já foi enviado com 2 itens, **When** uma checagem posterior
   (ainda dentro da janela da noite) encontra 1 item novo no boletim do SEI, **Then** um e-mail
   complementar é enviado contendo apenas o item novo.
3. **Given** o boletim do SEI do dia não traz nenhum andamento relevante, **When** o horário
   configurado do assinante chega, **Then** o assinante recebe um e-mail curto avisando que não
   há publicações previstas para o próximo DOU.
4. **Given** um assinante não habilitou a antecipação, **When** o sistema processa a rotina da
   noite, **Then** nenhum e-mail de antecipação é enviado a esse assinante.

---

### User Story 3 - Confirmação da manhã (Priority: P3)

Na manhã seguinte à antecipação, depois que o DOU real do dia é publicado, o mesmo assinante
recebe um e-mail confirmando que os andamentos antecipados na véspera foram de fato publicados —
ou apontando, em linguagem natural, quais NÃO apareceram no DOU real ("publicados, exceto: ...").
A concordância singular/plural do texto se ajusta quando há só um item. Se o CADE não publicou
nada no DOU real daquele dia, o assinante recebe um aviso curto nesse sentido, sem a linguagem de
"todos os itens abaixo".

**Why this priority**: É o fechamento do ciclo da História 2 — só faz sentido para quem recebeu
uma antecipação. Menor prioridade porque depende inteiramente das Histórias 1 e 2 já estarem
funcionando (mesmo motor de busca do DOU real da História 1, mesmo cadastro de antecipação da
História 2).

**Independent Test**: Testável isoladamente fornecendo um "antecipado da véspera" fixo (fixture)
e fixtures do DOU real do dia seguinte em três variações: tudo publicado, algo faltando, e nada
publicado. Verifica-se o texto e a lista de itens faltantes no e-mail gerado.

**Acceptance Scenarios**:

1. **Given** a véspera antecipou 3 andamentos e o DOU real do dia seguinte confirma os 3,
   **When** a checagem da manhã roda, **Then** o assinante recebe um e-mail confirmando que
   "todos os andamentos abaixo foram devidamente publicados", listando os 3 com o texto do DOU
   real.
2. **Given** a véspera antecipou 2 andamentos e o DOU real só confirma 1, **When** a checagem da
   manhã roda, **Then** o e-mail lista o andamento confirmado e menciona explicitamente qual
   ficou de fora ("... exceto [referência do andamento faltante]").
3. **Given** a véspera antecipou exatamente 1 andamento e ele não saiu no DOU real, **When** a
   checagem da manhã roda, **Then** o texto usa concordância no singular ("o andamento abaixo
   ...").
4. **Given** o CADE não publicou nada no DOU real do dia, **When** a checagem da manhã roda,
   **Then** o assinante recebe um aviso curto de que não houve publicações, sem a lista/linguagem
   de confirmação normal.
5. **Given** um assinante não recebeu antecipação na véspera (não habilitou a História 2 ou não
   havia nada a antecipar naquele dia), **When** a checagem da manhã roda, **Then** nenhum e-mail
   de confirmação é enviado a esse assinante nesse dia.

---

### Edge Cases

- Assinante cadastrado no digest do DOU mas com envio de e-mail pausado/silenciado (recurso já
  existente no sistema) não deve receber nenhum dos três e-mails enquanto durar a pausa.
- A mesma fonte listando o mesmo item mais de uma vez (ex.: a listagem do in.gov.br repetindo um
  artigo agrupado em mais de uma linha do índice, ou um edital citado duas vezes na Resenha): o
  item aparece uma única vez no e-mail, nunca duplicado. Como a busca usa uma fonte por vez
  (Resenha OU, na indisponibilidade dela, a listagem in.gov.br — nunca as duas na mesma execução
  do digest), a deduplicação é sempre dentro da fonte que respondeu naquele dia, não entre fontes
  diferentes.
- Item do DOU citando mais de um número de processo: o sistema usa a primeira referência tipada
  (ex.: "Processo Administrativo nº ...") como identificação do item para fins de deduplicação e
  do "exceto" da confirmação da manhã.
- Falha de rede/indisponibilidade das duas fontes dentro de toda a janela diária: nenhum e-mail é
  enviado naquele dia para aquele tipo de envio (digest/antecipação/confirmação), e a tentativa
  falha fica registrada no log de auditoria para permitir diagnóstico — não há reenvio fora da
  janela do dia.
- Assinante sem nenhum termo monitorado cadastrado: recebe o digest normalmente, apenas sem
  nenhum destaque amarelo.
- Pauta/ata do dia sem URL disponível na fonte: aparece no rodapé apenas com o texto/título,
  sem link quebrado.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST manter uma lista própria de assinantes do digest do DOU, cada um
  associado a um assinante existente do sistema, com inscrição independente de qualquer inscrição
  em processo monitorado específico.
- **FR-002**: O sistema MUST permitir, por assinante do digest do DOU, uma lista própria de termos
  monitorados (pessoa, empresa ou palavra-chave) usados apenas para o destaque visual do e-mail.
- **FR-003**: O sistema MUST buscar, uma vez por dia dentro de uma janela diária configurável, as
  publicações do CADE saídas no DOU do dia, usando como fonte primária a Resenha do CADE e, se
  ela não estiver disponível dentro da janela, a listagem pública do DOU (seções 1 e 3), filtrada
  para itens do CADE.
- **FR-004**: O sistema MUST respeitar um intervalo mínimo de 5 minutos entre tentativas de busca
  à mesma fonte (Resenha ou listagem do DOU), sem requisições paralelas, e MUST NOT buscar fora
  da janela diária configurada.
- **FR-005**: O sistema MUST enviar, a cada assinante ativo do digest, exatamente um e-mail de
  digest por dia, mesmo quando não houver nenhuma publicação do CADE naquele dia (aviso explícito
  de "sem publicações").
- **FR-006**: O sistema MUST formatar o conteúdo do digest em português, com título do caso e
  nomes de partes em negrito, despachos longos resumidos (início + conclusão), e blocos que
  contenham um termo monitorado do assinante destacados visualmente (ex.: fundo amarelo),
  destaque este calculado por assinante (o mesmo item pode aparecer destacado para um assinante e
  não para outro).
- **FR-007**: O sistema MUST incluir, no rodapé do e-mail de digest, uma referência (título e link
  para o DOU, quando disponível) a cada pauta/ata de sessão do CADE publicada naquele dia — sem
  anexar arquivo PDF nesta versão.
- **FR-008**: O sistema MUST permitir, por assinante, habilitar opcionalmente o recurso de
  antecipação da véspera, com um horário de envio configurável (com um padrão razoável quando não
  configurado).
- **FR-009**: Para assinantes com antecipação habilitada, o sistema MUST montar, a partir do
  boletim/resenha do SEI do próprio dia, um e-mail antecipando os andamentos que devem sair no
  DOU do dia seguinte, no horário configurado do assinante, e MUST enviar um e-mail complementar
  (apenas com itens novos, sem repetir os já antecipados) caso itens adicionais surjam no boletim
  do SEI antes de um horário-limite da noite.
- **FR-010**: Para assinantes com antecipação habilitada, o sistema MUST, na manhã seguinte,
  comparar o que foi antecipado na véspera com o DOU real do dia, e enviar um e-mail de
  confirmação indicando o que foi publicado e, quando houver diferença, apontando explicitamente
  o que ficou de fora ("... exceto ..."), com concordância singular/plural correta quando houver
  só um item.
- **FR-011**: O sistema MUST tratar dias sem nenhum item antecipado (véspera) ou sem nenhuma
  publicação real (manhã) com uma mensagem curta específica, sem usar a linguagem padrão de lista
  "todos os itens abaixo".
- **FR-012**: O sistema MUST NOT enviar mais de um e-mail do mesmo tipo (digest, antecipação,
  complemento da antecipação, confirmação) ao mesmo assinante no mesmo dia.
- **FR-013**: O sistema MUST registrar, para cada e-mail enviado por esta feature, um log de
  auditoria com assinante, tipo de envio, data e resultado (sucesso/falha), permitindo reconstruir
  o que foi enviado, para quem e quando.
- **FR-014**: O sistema MUST respeitar o estado de pausa/silêncio de notificações já existente do
  assinante — nenhum dos três e-mails desta feature é enviado enquanto o assinante estiver
  pausado.
- **FR-015**: O sistema MUST enviar os três tipos de e-mail exclusivamente por e-mail nesta
  versão (não Telegram, não WhatsApp).
- **FR-016**: O sistema MUST deduplicar itens repetidos dentro da mesma fonte de um dia (ex.: a
  listagem do in.gov.br citando o mesmo artigo em mais de uma linha do índice), tratando-os como
  um único item no e-mail. Não se aplica deduplicação entre Resenha e listagem do DOU: a busca do
  digest usa uma fonte por vez (fallback, nunca as duas juntas na mesma execução — ver FR-003).

### Key Entities *(include if feature involves data)*

- **Assinante do digest do DOU**: vínculo entre um assinante existente do sistema e a inscrição no
  digest do DOU; guarda se a antecipação da véspera está habilitada e o horário configurado de
  envio.
- **Termo monitorado (DOU)**: um termo (pessoa, empresa ou palavra-chave) cadastrado por um
  assinante do digest do DOU, usado para calcular o destaque visual no e-mail.
- **Envio do DOU**: registro de um e-mail enviado por esta feature (assinante, tipo — digest,
  antecipação, complemento, confirmação —, data de referência, resultado), usado para impedir
  duplicidade e para o log de auditoria.
- **Publicação do CADE no DOU**: um edital, despacho, ou pauta/ata do dia, com título, texto e
  (quando disponível) link para o artigo oficial — obtido da Resenha do CADE ou da listagem
  pública do DOU.
- **Antecipação da véspera**: o conjunto de andamentos identificados no boletim do SEI de um dia,
  associado ao assinante e à data, usado no dia seguinte para montar a confirmação da manhã.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Em pelo menos 95% dos dias úteis simulados em teste automatizado (com fixtures, sem
  depender de disponibilidade real das fontes externas), o e-mail de digest do dia é gerado e
  enviado dentro da janela diária configurada.
- **SC-002**: Nenhum assinante recebe mais de um e-mail do mesmo tipo (digest, antecipação,
  complemento, confirmação) no mesmo dia, verificável por auditoria do log de envios.
- **SC-003**: 100% dos e-mails enviados por esta feature ficam registrados no log de auditoria com
  assinante, tipo, data e resultado, permitindo reconstruir o histórico de envios de qualquer
  assinante.
- **SC-004**: Um leitor não técnico consegue identificar, sem ajuda, quais publicações do dia
  mencionam pessoas/empresas que ele monitora, apenas pelo destaque visual do e-mail (validável
  por teste manual de legibilidade com pelo menos um cenário de destaque presente e um ausente).
- **SC-005**: Em nenhum dia o sistema fica em silêncio: todo assinante ativo recebe uma mensagem
  (mesmo que seja só um aviso de "sem publicações") para cada tipo de envio a que está inscrito.

## Assumptions

- O modelo de assinante já existente no sistema (usado hoje para processos monitorados) é
  reaproveitado como identidade do assinante do digest do DOU; a inscrição no digest em si é uma
  entidade nova e independente.
- A fonte primária (Resenha do CADE) é tratada como uma página pública em escopo do Princípio II
  da constituição (v2.2.0, que já cobre explicitamente in.gov.br e sinc.cade.gov.br) — não há
  autenticação nem dado pessoal de partes além de nome/URL já públicos no DOU.
- O horário padrão de antecipação da véspera, quando o assinante não configura um horário próprio,
  é definido na fase de planejamento técnico (não é uma decisão de produto que precise travar a
  especificação) — um valor no fim da tarde/início da noite é adequado ao propósito do recurso.
- Leitura de PDF da seção do DOU (quando a listagem do in.gov.br vem vazia) e anexo de PDF de
  pauta/ata ficam fora de escopo nesta versão; ficam registradas como melhoria futura, sem
  bloquear a entrega das três histórias de usuário acima.
- "Dia útil" para fins de SC-001 segue o calendário de expediente do próprio CADE (dias em que o
  DOU costuma publicar); dias sem expediente não contam como falha de envio.
