# Research: Precedentes — dossiê de due diligence (fundação)

## Decisões de desenho desta fundação

Este documento registra as decisões de desenho do modelo de dados e da disciplina de revisão
humana desta primeira spec da iniciativa "Precedentes", e as alternativas descartadas:

## Versionamento de fato: uma tabela append-only, não uma tabela + histórico separado

- **Decisão**: `PrecedentFact` é a própria tabela de versões — cada linha é uma versão de um fato;
  corrigir insere uma linha nova (nunca `UPDATE` do valor), com uma self-FK `root` apontando para a
  primeira versão do grupo (`root=None` na própria raiz). `is_current=True` marca a versão vigente;
  corrigir desmarca a anterior e marca a nova.
- **Rationale**: expressa a garantia de append-only (nada é sobrescrito, histórico sempre
  consultável) como self-FK Django em vez de um inteiro de agrupamento manual — estrutura
  idiomática ao Django para essa garantia.
- **Alternativas descartadas**: uma tabela `PrecedentFact` (estado atual) + `PrecedentFactVersion`
  (histórico separado) — descartada por duplicar a modelagem sem ganho: uma única tabela
  append-only já garante o histórico completo, e ter duas tabelas exigiria manter as duas
  sincronizadas a cada escrita.

## Análise referencia a IDENTIDADE do fato (a raiz), não uma versão específica

- **Decisão**: `PrecedentAnalysis.facts` (M2M) sempre aponta para a linha-raiz (`root=None`) do
  grupo de versões de um fato — nunca para uma versão específica que pode deixar de ser a atual.
- **Rationale**: preserva FR-010 ("a referência aos fatos-base MUST permanecer íntegra mesmo quando
  um fato ganha uma nova versão") sem precisar mover a referência a cada correção — a raiz nunca é
  apagada por uma correção (só uma remoção de empresa a apaga, FR-012), então o link continua
  válido; "o valor atual" desse fato-base é resolvido, quando exibido, consultando
  `PrecedentFact.objects.filter(Q(id=root.id) | Q(root_id=root.id), is_current=True)`.
- **Alternativas descartadas**: guardar o texto do valor do fato no momento em que a análise foi
  criada (snapshot) — descartada porque contraria o próprio propósito de FR-010: a análise deve
  continuar apontando para o fato vivo (que pode ter sido corrigido desde então), não congelar um
  valor que pode estar desatualizado.

## Catálogo de campos: texto livre nesta versão, não um catálogo fixo

- **Decisão**: `PrecedentFact.campo` é `CharField` de texto livre nesta spec, não uma lista
  fechada/enum com catálogo de campos por grupo/sensibilidade.
- **Rationale**: sem pesquisa automática ainda (é só entrada manual), um catálogo fixo de campos
  seria estrutura sem uso real — o advogado digita o nome do campo que precisa (“faturamento”,
  “controladora”, o que for). Se/quando a extração automática (spec futura) precisar de um
  vocabulário fechado para casar campos extraídos com campos esperados, o catálogo entra nessa
  spec, não nesta.
- **Alternativas descartadas**: definir um catálogo fechado de campos agora — descartado por
  over-engineering (Princípio VIII): não há, nesta spec, nenhum consumidor que precise de um
  catálogo fechado.

## Papel da empresa: lista fixa e pequena, sem grafo societário automático

- **Decisão**: `PrecedentEntity.papel` usa `TextChoices` com poucos valores (`requerente`,
  `parte_identificada`, `outro`) — sem grafo de relações societárias/grupo econômico automático.
- **Rationale**: suficiente para o propósito desta spec (saber quem é quem no caso); o grafo
  societário (Art. 4º, relações de controle) é um recurso sofisticado, cortado deliberadamente
  para uma v1 — fica como melhoria futura, condicionada a quando a
  pesquisa societária automática (spec futura) alimentar esse grafo de verdade.

## Remoção de empresa: cascata de fatos + análises órfãs

- **Decisão**: remover uma `PrecedentEntity` cascade-remove seus `PrecedentFact` (via
  `on_delete=CASCADE`); em seguida, `services.remove_entity` remove explicitamente qualquer
  `PrecedentAnalysis` do caso que tenha ficado sem nenhum fato-base restante (todos os seus fatos
  eram só dessa empresa).
- **Rationale**: atende FR-012 ("remove fatos e análises que dependem só dela") sem exigir uma
  regra de cascata mais complexa no banco — a cascata de fato já é nativa do Django; a limpeza de
  análise órfã é uma checagem simples no service, não uma constraint de banco.

## Sem gate de constituição nesta spec

- **Decisão/confirmação**: nenhuma chamada de rede, nenhuma fonte externa, nenhuma IA nesta spec —
  logo, nenhum Princípio II/emenda de constituição entra em jogo aqui. As specs seguintes da
  iniciativa (pesquisa societária: SEC/EDGAR, CVM, Receita Federal; jurisprudência: Solr do CADE)
  precisarão de sua própria avaliação — a de pesquisa societária quase certamente precisa de uma
  emenda nova (3 domínios não cobertos hoje); a de jurisprudência reaproveita o host já coberto
  pela emenda v2.2.0 (mesmo `sinc.cade.gov.br`, coleção diferente).
