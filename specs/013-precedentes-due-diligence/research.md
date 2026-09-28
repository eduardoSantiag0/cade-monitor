# Research: Precedentes — dossiê de due diligence (fundação)

## Fonte do desenho: 6 agentes de pesquisa paralelos sobre o Mesk

Antes desta spec, 6 pesquisas paralelas leram as ~13.500 linhas de `cademon/prec_*.py` +
`precedentes.py` + `web_precedentes.py` (20 arquivos). Resumo das decisões que vieram dessa
pesquisa e foram aplicadas ao escopo desta primeira spec:

## Versionamento de fato: uma tabela append-only, não uma tabela + histórico separado

- **Decisão**: `PrecedentFact` é a própria tabela de versões — cada linha é uma versão de um fato;
  corrigir insere uma linha nova (nunca `UPDATE` do valor), com uma self-FK `root` apontando para a
  primeira versão do grupo (`root=None` na própria raiz). `is_current=True` marca a versão vigente;
  corrigir desmarca a anterior e marca a nova.
- **Rationale**: é exatamente o padrão `raiz_id`/`ativo` do Mesk (`prec_facts`, confirmado pela
  pesquisa de cross-análise/revisão), só que expresso como self-FK Django em vez de um inteiro de
  agrupamento manual — mesma garantia (nada é sobrescrito, histórico sempre consultável), estrutura
  mais idiomática ao Django.
- **Alternativas descartadas**: uma tabela `PrecedentFact` (estado atual) + `PrecedentFactVersion`
  (histórico separado) — descartada por duplicar a modelagem sem ganho: o Mesk já prova que uma
  única tabela append-only basta, e ter duas tabelas exigiria manter as duas sincronizadas a cada
  escrita.

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
  fechada/enum como o `prec_campos.py` do Mesk (catálogo de ~204 linhas com grupos/sensibilidade).
- **Rationale**: sem pesquisa automática ainda (é só entrada manual), um catálogo fixo de campos
  seria estrutura sem uso real — o advogado digita o nome do campo que precisa (“faturamento”,
  “controladora”, o que for). Se/quando a extração automática (spec futura) precisar de um
  vocabulário fechado para casar campos extraídos com campos esperados, o catálogo entra nessa
  spec, não nesta.
- **Alternativas descartadas**: portar `prec_campos.py` inteiro agora — descartado por
  over-engineering (Princípio VIII): não há, nesta spec, nenhum consumidor que precise de um
  catálogo fechado.

## Papel da empresa: lista fixa e pequena, sem grafo societário automático

- **Decisão**: `PrecedentEntity.papel` usa `TextChoices` com poucos valores (`requerente`,
  `parte_identificada`, `outro`) — sem o grafo de relações societárias
  (`prec_entity_relations`)/grupo econômico automático do Mesk.
- **Rationale**: suficiente para o propósito desta spec (saber quem é quem no caso); o grafo
  societário (Art. 4º, relações de controle) é um recurso sofisticado que a própria pesquisa de
  cross-análise recomendou cortar para uma v1 — fica como melhoria futura, condicionada a quando a
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
