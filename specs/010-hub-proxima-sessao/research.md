# Research: Próxima sessão de julgamento no dashboard

## Cache compartilhado entre view e worker

- **Decisão**: usar o backend `django.core.cache.backends.db.DatabaseCache` (`CACHES['default']`),
  com uma tabela criada por `python manage.py createcachetable`, em vez de um modelo Django
  próprio.
- **Rationale**: o requisito (FR-004/FR-005) é exatamente o que o cache framework do Django já
  resolve — par chave/valor com TTL, compartilhado entre processos via Postgres. Escrever um
  modelo (`HubCache`, com `key`/`value`/`expires_at`) seria reimplementar, com mais código e uma
  migration a mais, algo que o framework já embute (Princípio VIII, "não adicionar"). Diferente da
  feature 009 (`DouFetchState`/`DouAnticipation`), que tinha campos e chaves de negócio próprias
  (fonte, assinante) que não caberiam bem num cache genérico de string→valor, aqui os dois dados
  (lista de sessões, URL da pauta) são exatamente esse caso — valor serializável sob uma chave.
- **Alternativas descartadas**: (a) `LocMemCache` (padrão do Django sem configuração) — descartada
  porque não é compartilhado entre o processo web (Gunicorn) e o container do worker, que são
  processos/containers separados neste projeto (`docker-compose.yml`); um cache em memória local
  faria o worker atualizar um cache que a view nunca veria. (b) Redis — já existe como opção no
  projeto (`PROCESS_HASH_REDIS_*`), mas o Princípio I restringe seu uso exclusivamente ao cache de
  hash de processo ("MUST NOT: Usar Redis para qualquer outra finalidade... sem nova emenda a este
  princípio"); usar Redis aqui exigiria emenda, enquanto `DatabaseCache` resolve sem tocar a
  constituição.

## `www.gov.br/cade` como fonte em escopo do Princípio II

- **Decisão**: tratar `www.gov.br/cade/...` (calendário e pautas de sessão) como já coberto por
  "páginas públicas do CADE" no texto atual do Princípio II, sem emenda.
- **Rationale**: é o próprio CADE publicando conteúdo no espaço que lhe é reservado dentro do
  portal unificado do governo federal (`gov.br`) — mesma autoria e mesmo propósito informativo de
  `cade.gov.br`/`sei.cade.gov.br`, só que hospedado num domínio compartilhado por desenho do
  governo federal (todos os órgãos usam `gov.br/<sigla>`). Isso é diferente do caso do DOU
  (feature 009), onde `in.gov.br` e `sinc.cade.gov.br` são portais de OUTRA natureza (o Diário
  Oficial da União, publicado pela Imprensa Nacional, não pelo CADE) — ali a emenda documentou uma
  classe de fonte genuinamente nova. Aqui não há essa distinção: é conteúdo do CADE, só que num
  outro canto do mesmo domínio institucional.
- **Alternativas descartadas**: propor uma emenda "por precaução" mesmo sem necessidade clara —
  descartada para não desvalorizar o processo de emenda (reservá-lo para mudanças de escopo reais,
  como o de fato ocorreu na feature 009).

## Escopo excluído do `hub.py` original (Mesk)

- **Decisão**: portar só "próxima sessão" + "pauta"; excluir "transmissão ao vivo no YouTube" e
  "cidade do visitante" (geo-IP).
- **Rationale**: o `hub.py` do Mesk foi escrito para a capa pública de um site voltado a
  visitantes externos (a cidade do visitante é literalmente um dateline de página pública, e o
  card de "ao vivo agora" é conteúdo de vitrine). O dashboard do cade-monitor é autenticado, para
  a própria equipe que já monitora os processos — geo-IP de quem acessa não tem propósito ali, e
  "ao vivo agora" tem valor bem menor para quem já acompanha os processos pelo sistema. Excluir
  os dois também evita precisar avaliar `youtube.com` (domínio de terceiro, fora do escopo atual
  do Princípio II) e uma chamada a um serviço de geolocalização de IP de terceiro
  (`ip-api.com`) para cada visitante — nenhum dos dois se paga pelo valor que teriam aqui.
- **Alternativas descartadas**: portar tudo por fidelidade ao Mesk — descartada porque o
  princípio orientador desta iniciativa (README do brief da sessão) é portar o *comportamento*
  melhorando onde fizer sentido, não replicar código por replicar; aqui replicar sem pensar no
  público-alvo real (equipe interna, não visitante público) seria a definição de over-engineering
  especulativo.
- Os helpers de formatação de data/prazo (`data_por_extenso`, `dias_ate`, `prazo_selo`) do
  `hub.py` original ficam de fora por pertencerem, em espírito, à feature de Agenda/Prazos
  (`calendario.py`), ainda não portada — evita duplicar essa lógica antes dela existir.

## Validação ao vivo (a fazer durante a implementação, documentar aqui o resultado)

Seguindo o padrão das features 008/009: antes de considerar a feature pronta, validar com 1-2
chamadas reais (nunca em loop/teste automatizado):

- `https://www.gov.br/cade/pt-br/assuntos/sessoes/calendario-de-sessoes`: confirmar que o HTML
  ainda seque o padrão ano→mês→dia que `sessoes_do_html` (adaptado do Mesk) assume.
- `https://www.gov.br/cade/pt-br/assuntos/sessoes/sessoes%20de%20julgamento/{ano}`: confirmar que
  os links de PDF em `cdn.cade.gov.br/.../{ano}/{numero}/...` com "pauta" no nome do arquivo ainda
  existem no formato assumido.

## Correção pós-implementação (validação ao vivo, 2026-09-28)

Duas chamadas reais (calendário de sessões + página anual de pautas de 2026) confirmaram que,
diferente do achado da feature 009 (DOU), **o formato assumido bateu com a realidade nas duas
fontes, sem precisar de correção**:

- `sessoes_do_html` extraiu corretamente 136 sessões do calendário real (2020–2026), incluindo a
  sessão futura mais próxima da data de validação (`273ª Sessão Ordinária`, `2026-10-07`) e casos
  de sessão marcada como "não realizada" (`Sessão Extraordinária (sessão não realizada)`) — que
  ainda entram na lista (contêm "sessão" no título) mas não têm tratamento especial; como o
  cartão só mostra data+título, isso é aceitável no v1 (não distingue sessão cancelada da
  realizada).
- `pauta_do_html` encontrou corretamente os PDFs de pauta das sessões já publicadas (ex.: sessões
  269 e 271, com nomes de arquivo bem variados — `"Pauta 271.pdf"`,
  `"SEI_1789486_Pauta_Sessao_de_Julgamento_269__SOJ.pdf"` — todos batendo com o filtro `'pauta' in
  nome.lower()`) e devolveu `''` corretamente para a sessão 273 (a próxima), cuja pauta ainda não
  tinha sido publicada no momento do teste — comportamento esperado de FR-006, não um bug.

Nenhuma mudança em `apps/dashboard/hub.py` foi necessária após esta validação.
