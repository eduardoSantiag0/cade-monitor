# Research: Digest diário do DOU

## Fontes externas e ordem de fallback

- **Decisão**: fonte primária = Resenha do CADE (`sinc.cade.gov.br`, endpoint Solr público,
  `colecao:resenha_dou AND data_ordem:<yyyymmdd>`), um documento HTML por dia com editais e
  despachos já filtrados para o CADE. Fallback = listagem pública do DOU
  (`www.in.gov.br/leiturajornal?data=DD-MM-AAAA&secao=dou1|dou3`), filtrada por `hierarchyStr`
  contendo "conselho administrativo de defesa econ".
- **Rationale**: a Resenha é uma única chamada HTTP, estável, já filtrada por CADE, sem
  anti-bot conhecido — o caminho barato. O in.gov.br é anti-bot/instável (precisa de
  `User-Agent` de navegador e retries) e traz muito mais ruído (todo o DOU, não só CADE) — só vale
  o custo quando a Resenha do dia ainda não saiu.
- **Alternativas descartadas**: (a) ler só in.gov.br sempre — descartado por ser a fonte instável
  e mais cara, sem necessidade quando a Resenha já responde; (b) fallback por leitura de PDF de
  página quando a listagem do in.gov.br vem vazia — descartado nesta versão (spec.md, Assumptions)
  por exigir `pypdf` e lógica de paginação/verificação de autenticidade sem benefício proporcional
  ao esforço para um v1; fica registrado como melhoria futura.

## Ata/pauta do dia

- **Decisão**: aparecem no rodapé do e-mail como título + link para o artigo do DOU, sem anexo de
  PDF.
- **Rationale**: anexar o PDF real exigiria imprimir a página do in.gov.br via navegador headless
  — uma dependência de runtime nova (Playwright/Chromium) que contraria o Princípio I/VIII
  deste projeto (stdlib preferida, dependências novas exigem justificativa por escrito). Link
  cobre o mesmo propósito informativo sem o custo.
- **Alternativas descartadas**: baixar o PDF oficial via `pesquisa.in.gov.br` sem imprimir a
  página — não avaliado como viável nesta fase; ficaria como pesquisa própria de uma melhoria futura.

## Cadência de busca (5 min / janela diária)

- **Decisão**: um marcador de "última tentativa" por fonte (`DouFetchState`, ver data-model.md),
  consultado no início de cada chamada de busca; se `now - last_attempt_at < 5min`, a busca não
  roda neste tick do worker. Janela diária (ex.: manhã para o digest) é um horário de início/fim
  configurável via variável de ambiente, comparado ao relógio local (`TIME_ZONE=America/Sao_Paulo`
  já configurado no projeto).
- **Rationale**: atende literalmente a emenda do Princípio II (v2.2.0) com a menor estrutura
  possível — um registro por fonte, não um sistema de cache genérico. Reaproveita o padrão já
  existente no projeto de "marcador de estado consultado a cada tick do worker" (o próprio
  `run_worker` já faz isso para processos vencidos via `get_due_processes`).
- **Alternativas descartadas**: lógica completa de acumulação+estabilidade por janela (no estilo
  `DOU_ACC_*`: janela 06:40–11:00, "sem item novo por 20 min" = completo) — descartada por
  over-engineering: a spec (P1) não exige detectar "completude" da edição, só buscar dentro da
  janela e enviar o que houver: uma lógica de estabilidade full traria complexidade sem requisito
  correspondente. Fica anotada como possível refinamento se, na prática, o digest sair incompleto
  com frequência.

## Antecipação da véspera e confirmação da manhã (P2/P3)

- **Decisão**: a antecipação (P2) reaproveita a extração de andamentos já existente em
  `apps/monitoring/extractors.py` sobre o boletim/resenha do SEI (mesma fonte que o monitoramento
  de processo já lê), não uma fonte nova. O resultado do dia é persistido em um único campo JSON
  (`DouAnticipation.items`) por assinante+data, consultado na manhã seguinte para montar o "exceto
  ...".
- **Rationale**: evita criar uma tabela relacional nova só para guardar uma lista de itens que é
  sempre lida e escrita como unidade (nunca consultada item a item) — JSON num único modelo é o
  suficiente e mais simples (Princípio VIII).
- **Alternativas descartadas**: tabela `DouAnticipationItem` normalizada (um registro por item
  antecipado) — descartada por não haver nenhum requisito que precise consultar itens
  individualmente fora do contexto "todos os itens desta antecipação".

## Validação ao vivo (a fazer durante a implementação, documentar aqui o resultado)

Seguindo o padrão da feature 008 (item 6 do processo): antes de considerar a feature pronta,
validar com 1-2 chamadas reais (nunca em loop/teste automatizado):

- Resenha do CADE: confirmar o formato exato de resposta do endpoint Solr (`sinc.cade.gov.br`) e
  a estrutura HTML dentro do campo `conteudo`, para calibrar o parser contra dados reais em vez de
  só uma suposição estática.
- Listagem in.gov.br: confirmar que o filtro por `hierarchyStr` ainda funciona no formato atual do
  site e que o `User-Agent`/retries do padrão de `apps/monitoring/clients.py` bastam (sem precisar
  de um backoff mais agressivo que o já configurado).

## Correção pós-implementação (validação ao vivo, 2026-09-28)

Duas chamadas reais (uma à Resenha, uma à listagem in.gov.br, seção `dou1`) revelaram que o
formato assumido no design original estava errado nos dois casos — nenhum dos dois usa a
estrutura "Editais/Despachos/Atas" com cabeçalhos em negrito nem classes CSS previsíveis que o
plano original presumia. `apps/dou/parsers.py` foi reescrito para refletir a realidade abaixo.

### Resenha do CADE (`sinc.cade.gov.br`)

- O endpoint e os parâmetros (`q=colecao:resenha_dou AND data_ordem:AAAAMMDD&fl=conteudo&rows=1
  &wt=json`) estavam corretos — resposta 200, um único documento com o campo `conteudo` trazendo
  o HTML da resenha inteira do dia.
- **Divergência**: não existe nenhum cabeçalho em negrito "Editais"/"Despachos"/"Atas". A estrutura
  real é: `<div><strong>Seção N</strong></div>` → `<div><strong>NOME DO ÓRGÃO</strong></div>` →
  uma sequência de itens, cada um com um `<div><strong>TÍTULO DO ATO</strong></div>` (ex.:
  "DESPACHO Nº 44, DE 23 DE SETEMBRO DE 2026", ou um lote como "DESPACHOS DO
  SUPERINTENDENTE-GERAL" com subitens "Nº 1.263/2026") seguido de `<div>`s de corpo em texto
  normal, até o próximo título ou até a próxima seção/órgão. Um mesmo dia mistura vários órgãos na
  mesma edição (ex.: Seção 2 trouxe uma portaria de pessoal do Ministério da Gestão que só cita o
  CADE de passagem, como local de exercício de uma servidora — não é publicação do CADE e não pode
  entrar no digest).
- **Correção aplicada**: `parse_resenha_html` agora percorre os blocos em ordem, rastreia a
  seção/órgão corrente e só acumula texto enquanto o órgão for reconhecido como CADE (reaproveita
  `is_cade_item`, o mesmo fold usado no filtro do in.gov.br). Seção 1 vira o bucket `despachos`;
  Seção 3 vira `editais` (mapeamento best-effort — Seção 3 do DOU é onde entram os
  editais/avisos/extratos do CADE). Dentro do texto já filtrado por CADE, a divisão em itens
  continua pelo `_CASE_TITLE_RE` (Ato de Concentração/Processo Administrativo/etc.), que já
  funcionava corretamente para esse propósito.
- **Atas/pautas**: no dia validado não saiu nenhuma ata/pauta de sessão na Resenha, então não há
  exemplo real para calibrar a extração. Em vez de uma heurística especulativa, `parse_resenha_html`
  devolve `atas: []` por ora — `render.py` já sabe exibir o rodapé assim que `atas` vier populada
  por qualquer fonte futura (é só uma lista de `{'titulo', 'url'}`). Fica como acompanhamento: a
  próxima vez que uma ata sair na Resenha, capturar o HTML real e implementar a extração
  correspondente.

### Listagem in.gov.br (`www.in.gov.br/leiturajornal`)

- **Divergência maior**: a página é majoritariamente renderizada em JavaScript (Liferay); não há
  `class="materia-item"`/`class="orgao"` nem qualquer marcação HTML estática previsível para os
  itens do dia (a suposição original, sem validação, estava errada). Os itens do dia vêm embutidos
  como JSON dentro de `<script id="params" type="application/json">{"jsonArray": [...], ...}
  </script>`, um item por publicação, com os campos: `title`, `content` (resumo, ~400 caracteres —
  **não** é o texto integral do ato), `artType` (ex. `"Despacho"`, presumivelmente `"Edital"` para
  editais — não confirmado ao vivo por falta de um edital no dia testado), `hierarchyStr` (caminho
  completo do órgão, ex. `"Ministério da Justiça e Segurança Pública/Conselho Administrativo de
  Defesa Econômica/Superintendência-Geral"`) e `urlTitle` (slug para montar a URL do artigo:
  `https://www.in.gov.br/web/dou/-/<urlTitle>`).
- **Correção aplicada**: `parse_ingov_listing` extrai e faz `json.loads` do conteúdo desse script,
  filtra por `hierarchyStr` (mesmo `is_cade_item` de antes) e classifica edital vs. despacho pelo
  campo `artType` (`fold(artType) == 'edital'` → editais; qualquer outro valor → despachos), em vez
  de inferir pelo título.
- **Limitação conhecida (já prevista como fora de escopo)**: como `content` é só um resumo curto,
  o digest via fallback in.gov.br sai com texto mais curto que via Resenha (que traz o ato
  completo). Abrir cada artigo pela URL de `urlTitle` para pegar o texto integral já estava listado
  como "nice-to-have, defer" no brief de design original — confirmado como o comportamento real a
  melhorar numa iteração futura, não um bloqueio para o v1.

### Publicações do SEI (`sei.cade.gov.br`, usado pela antecipação — User Story 2)

**Validado ao vivo em 2026-09-28 (2 chamadas: 1ª rodada GET+POST, 2ª rodada GET+POST) — achado
negativo, ainda sem solução.** A implementação original desta rodada usava parâmetros de query
GET inventados (`rdo_data_publicacao`, `dta_inicio`, `dta_fim`), que a primeira chamada real
mostrou estarem completamente errados: `SEI_PUBLICATIONS_URL` é o formulário de busca
`frmPublicacaoPesquisa` (`method="post"`, mesma URL como `action`), com campos
`rdoDataPublicacao` (radio `H`/`I`/`E`, `E` = período explícito, pré-marcado), `txtDataInicio`/
`txtDataFim` (texto, formato `DD/MM/AAAA`) e `selOrgao[]` (só uma opção: `value="0"` = CADE).

**Correção aplicada**: `fetch_sei_publications` agora segue o mesmo padrão de
`apps/monitoring/extractors.py::_resolve_process_detail` (GET inicial para ler os defaults do
formulário via `extract_input_defaults`, reaproveitado por import — não duplicado —, depois POST
com esses defaults sobrescritos pelos campos de busca).

**Mas a segunda chamada real (já com essa correção) mostrou que isso ainda não basta**: o POST
devolve a mesma casca da página de busca (o mesmo HTML do formulário, incluindo o CSS de um
`#tblPublicacoes` que nunca chega a existir no corpo da resposta) — não uma tabela de resultados.
Diferente do formulário de busca de processo (`CADE_SEARCH_URL`, feature 008), que aceita POST
direto, o de publicações parece depender do `onsubmit="return onSubmitForm();"` do formulário —
provável busca assíncrona (AJAX, contra um endpoint ainda não identificado, ex.
`InfraAjax.js`/`controlador_ajax.php`) em vez de um POST síncrono com reload de página. Não há,
nos campos estáticos do formulário, nenhuma pista do endpoint/parâmetros AJAX reais — identificar
isso exigiria inspecionar o tráfego de rede de uma sessão de navegador real (fora do orçamento de
"1-2 chamadas" desta validação, e potencialmente exigindo uma dependência de navegador headless
que contraria o Princípio I/VIII).

**Decisão de segurança tomada agora**: em vez de arriscar mandar lixo (o texto da casca da
página — menu, script, CSS — não tem nenhuma citação de caso) como se fosse uma publicação real,
`parse_sei_publications` foi ajustado para **não** cair no fallback de "nenhuma citação
reconhecida → devolve o texto inteiro como um item" que `_split_items_by_case_title` usa para a
Resenha (lá é seguro, porque o texto já filtrado por CADE é sempre conteúdo real). Sem nenhuma
citação de caso reconhecida, `parse_sei_publications` devolve `[]` — que já vira corretamente o
aviso de "sem publicações previstas" (FR-011), nunca um e-mail com conteúdo inventado.

**Estado resultante**: User Story 2 (antecipação) e User Story 3 (confirmação, que depende de
uma antecipação existir) estão implementadas, testadas (com fixtures que simulam o formato de
item esperado) e **seguras** (nunca mandam lixo), mas **não comprovadamente funcionais contra o
SEI real** — hoje, na prática, `run_anticipation_window` sempre vai mandar o e-mail de "sem
publicações previstas", nunca um digest real, até que o endpoint AJAX correto seja identificado.
Acompanhamento pendente e explícito antes de considerar User Story 2/3 prontas para produção —
não é um bloqueio para mergear User Story 1 (digest diário, que não depende disso), mas é um
gap real de funcionalidade que não deve ficar silencioso.
