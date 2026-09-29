# Research: Pacote de autos (documentos públicos) do processo

## Fonte da lista de documentos e das URLs de download

- **Decisão**: dentro do job, fazer um fetch fresco da página pública do processo
  (`apps/monitoring/clients.py::get_snapshot`, que já preenche `Snapshot.html` quando necessário
  para extração de links) em vez de reaproveitar `MonitoredProcess.last_text` (que é só o texto
  normalizado, sem HTML, guardado do último ciclo de monitoramento). A lista declarada de
  documentos vem de `extract_protocol_records(snapshot.text)`; as URLs de download vêm de
  `extract_document_links(snapshot.html, snapshot.url)`.
- **Rationale**: um pacote montado sobre um
  snapshot desatualizado pode divergir silenciosamente do processo real (documento novo desde o
  último ciclo de monitoramento, prazo de 30 min por processo). Como o pedido de pacote é sob
  demanda (não em todo ciclo do worker), o custo de um fetch fresco por pedido é aceitável.
- **Alternativas descartadas**: reaproveitar `MonitoredProcess.last_text` diretamente — descartada
  porque não teria as URLs de download (só texto normalizado, sem HTML) e poderia estar até 30 min
  desatualizada.

## Download de cada documento

- **Decisão**: reaproveitar `apps/monitoring/clients.py::download_document(url, record, timeout,
  user_agent, max_bytes=None)` sem alteração de assinatura — já aplica
  `DOCUMENT_DOWNLOAD_MAX_BYTES`, já trata timeout/retry via a política existente.
- **Rationale**: é a mesma função já usada por `collect_new_documents` para anexar documentos a
  notificações — reimplementar o download seria duplicação sem benefício.

## Placeholder de documento indisponível — corroboração obrigatória

- **Decisão**: um documento da Lista de Protocolos sem URL em `extract_document_links` só vira
  placeholder `.txt` quando há, nos dados já extraídos do processo (andamentos via
  `extract_movement_records`, ou o próprio texto da Lista de Protocolos), uma menção que explique
  a ausência (ex.: termos como "restrito", "sigiloso", "indisponível", "removido" próximos à
  referência do documento). Sem essa corroboração, o documento conta como divergência para a
  checagem de integridade (FR-008/FR-009) — nunca vira um placeholder por suposição.
- **Rationale**: um documento sem
  link E sem explicação é sinal de bug de extração (ou de um tipo de ausência não previsto), não
  de "documento restrito" — tratar os dois casos como a mesma coisa esconderia bugs atrás de um
  pacote aparentemente completo.
- **Alternativas descartadas**: tratar TODO documento sem link como placeholder automático (mais
  simples, mas reintroduz o risco de mascarar falha de extração real — rejeitado por
  contrariar SC-003/FR-009, o requisito central de "nunca entregar incompleto silenciosamente").

## Execução em segundo plano (nunca no request)

- **Decisão**: `AutosPackageJob` como fila de 1 linha por (processo, ainda não expirado); pedido
  do usuário (view) só cria/reaproveita a linha com status `queued`; `run_worker` processa jobs
  `queued`/`processing` a cada ciclo, um documento por vez, com
  `time.sleep(settings.SLEEP_BETWEEN_REQUESTS_SECONDS)` entre downloads (mesma variável já usada
  pelo monitoramento de processo).
- **Rationale**: processos grandes (centenas de documentos) podem levar minutos — inaceitável
  dentro do timeout de um request HTTP e do único worker Gunicorn (Princípio I). O padrão
  "linha na tabela + `run_worker` processa" já é o mesmo usado para ações do bot do Telegram que
  dependem do SEI (constitution.md, Princípio I: "Ações do bot que consultam o SEI... são
  gravadas numa tabela do banco e executadas pelo run_worker").
- **Alternativas descartadas**: processar dentro do request com um limite de tempo curto e
  paginação manual pelo usuário — descartada por ser pior experiência (usuário precisa ficar
  recarregando) sem simplificar a implementação; o padrão fila+worker já existe no projeto.

## Escrita do ZIP (memória)

- **Decisão**: escrever o ZIP incrementalmente em disco (`zipfile.ZipFile` aberto em modo `'w'`
  sobre um arquivo, `writestr`/`write` por entrada, nunca montando todos os bytes de todos os
  documentos em memória de uma vez antes de zipar).
- **Rationale**: Princípio I (≤512MB RAM) — um processo de centenas de documentos poderia somar
  dezenas/centenas de MB se tudo ficasse em memória simultaneamente antes da escrita.

## Expiração do pacote pronto

- **Decisão**: `AutosPackageJob` ganha um campo de expiração (`expires_at`, calculado na conclusão
  como `now + AUTOS_PACKAGE_TTL_SECONDS`); um passo de limpeza (dentro do mesmo `run_worker`, ou
  reaproveitando o padrão já existente de `cleanup_snapshots`) remove o arquivo em disco e marca o
  job como expirado após esse prazo.
- **Rationale**: evita acúmulo indefinido de arquivos grandes em disco (Princípio I) — o pacote é
  descartável, já que o SEI é a fonte de verdade sempre disponível para gerar outro.
- **Alternativas descartadas**: manter pacotes para sempre — descartada por crescimento de disco
  sem limite, sem benefício proporcional (o SEI está sempre disponível para gerar de novo).

## Documento que é, ele mesmo, um ZIP

- **Decisão**: incluído como está no pacote final (um `.zip` dentro do `.zip`), sem abrir/expandir
  seu conteúdo nesta versão (spec.md, Assumptions/FR-013).
- **Rationale**: expandir recursivamente introduz risco de zip-bomb/path-traversal, que exigiria
  uma profundidade máxima e defesas específicas — complexidade desproporcional para o v1, sem
  requisito que exija abrir o conteúdo.

## Validação ao vivo (a fazer durante a implementação, documentar aqui o resultado)

Seguindo o padrão das features 008-011: antes de considerar pronta, validar com 1-2 chamadas reais
(nunca em loop) contra um processo público real conhecido, com documentos suficientes para
exercitar pelo menos um caso de documento sem link (se existir um processo real com esse caso à
mão) — confirmar que `extract_document_links` sobre o HTML fresco da página encontra as mesmas
URLs que `download_document` já usa hoje para anexos de notificação (é a mesma função, mas vale
confirmar o fluxo ponta a ponta pelo menos uma vez contra dado real).

## Correção pós-implementação (validação ao vivo, 2026-09-28)

**2 chamadas reais** contra o processo público `08700.005905/2026-38` (já usado como exemplo na
feature 008):

1. `get_snapshot` + `extract_protocol_records` + `extract_document_links`: 23 documentos
   declarados na Lista de Protocolos, **23 com link resolvido** — nenhum caso de "sem link" nesse
   processo específico (não foi possível validar ao vivo o caminho de placeholder/divergência
   contra dado real; ficou coberto só pelos fixtures de teste, como o quickstart.md já previa como
   possibilidade).
2. `download_document` no primeiro documento (`1773551`, "Notificação"): baixou com sucesso —
   `1773551-Notificacao.pdf`, `application/pdf`, 393.873 bytes.

**Divergência encontrada e corrigida ANTES desta rodada** (durante a escrita dos fixtures de
teste, não contra a fonte real): os fixtures HTML originais usavam um padrão de URL inventado
(`documento.php?id=...`), que não batia com nenhum dos marcadores reais que
`extract_document_links`/`_looks_like_document_url` exigem
(`md_pesq_documento_consulta_externa.php`, `documento_consulta_externa`,
`documento_download_anexo`, `controlador.php?acao=documento`, definidos em
`apps/monitoring/extractors.py::DOCUMENT_LINK_MARKERS`) — os testes automatizados pegaram isso
imediatamente (todo link saía vazio, todo pacote "divergia"), antes mesmo da validação ao vivo.
Fixtures corrigidos para usar `md_pesq_documento_consulta_externa.php?id_documento=...`, o mesmo
padrão confirmado agora contra o processo real.

**Nenhuma divergência entre o assumido em `builder.py`/`services.py` e o comportamento real das
funções já existentes de `apps/monitoring/clients.py`** — `get_snapshot`, `extract_document_links`
e `download_document` se comportaram exatamente como o contrato já documentava, sem necessidade de
ajuste em `apps/autos/`.
