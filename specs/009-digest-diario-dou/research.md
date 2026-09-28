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
- **Rationale**: anexar o PDF real exige imprimir a página do in.gov.br via navegador headless no
  Mesk — uma dependência de runtime nova (Playwright/Chromium) que contraria o Princípio I/VIII
  deste projeto (stdlib preferida, dependências novas exigem justificativa por escrito). Link
  cobre o mesmo propósito informativo sem o custo.
- **Alternativas descartadas**: baixar o PDF oficial via `pesquisa.in.gov.br` sem imprimir a
  página — não avaliado como viável nesta fase porque o Mesk não usa esse caminho para atas (só
  para o fallback de seção vazia); ficaria como pesquisa própria de uma melhoria futura.

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
- **Alternativas descartadas**: réplica completa da lógica de acumulação+estabilidade do Mesk
  (`DOU_ACC_*`, janela 06:40–11:00, "sem item novo por 20 min" = completo) — descartada por
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
  a estrutura HTML dentro do campo `conteudo`, para calibrar o parser sem depender só da
  descrição do código do Mesk.
- Listagem in.gov.br: confirmar que o filtro por `hierarchyStr` ainda funciona no formato atual do
  site e que o `User-Agent`/retries do padrão de `apps/monitoring/clients.py` bastam (sem precisar
  do backoff mais agressivo que o Mesk usa).

*(Seção "Correção pós-implementação" a ser adicionada aqui, se a realidade divergir do que este
research.md assume, seguindo o modelo de `specs/008-endurecer-scraper-sei/research.md`, item 6.)*
