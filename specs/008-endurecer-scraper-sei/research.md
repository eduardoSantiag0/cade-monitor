# Research: Endurecimento da resolução de processo no SEI/CADE

Nenhum item do Technical Context ficou como `NEEDS CLARIFICATION` — a stack, o padrão de testes e
a estratégia técnica já estão determinados pelo código existente (`apps/monitoring/`) e pelo
comportamento já validado em produção no scraper do projeto irmão Mesk (`cademon/scraper.py`).
Este documento registra as decisões e as alternativas descartadas.

## 1. Estratégia de múltiplas buscas (protocolo → texto → nº de documento)

- **Decision**: `_fetch_by_process_number` passa a montar até três payloads de POST distintos —
  variando `txtProtocoloPesquisa`, depois adicionando `q`/`as_q`/`txtTextoPesquisa`, depois
  também `txtNumeroDocumentoPesquisa` — e tenta cada um em sequência, parando no primeiro que
  `extract_process_detail_url` conseguir resolver.
- **Rationale**: é exatamente o que `fetch_cade_search_snapshot` faz em `cademon/scraper.py`
  (linhas ~2100–2201), testado ao vivo contra `sei.cade.gov.br` numa verificação anterior desta
  mesma sessão de trabalho. Resolve o cenário relatado (User Story 1): processos que só aparecem
  na busca por texto livre ou por número de documento.
- **Alternatives considered**:
  - Manter uma única estratégia e só documentar a limitação — rejeitado, é exatamente a falha
    silenciosa que a feature existe para corrigir.
  - Tentar as três estratégias em paralelo (requisições concorrentes) — rejeitado, viola o
    Princípio II (sem requisições paralelas/burst) sem necessidade: a maioria dos processos já
    resolve na primeira tentativa, então o custo médio adicional é baixo.

## 2. Leitura dinâmica dos campos ocultos do formulário

- **Decision**: antes do primeiro POST, fazer um GET em `CADE_SEARCH_URL` e extrair todos os
  `<input>` com `name`/`value` da página (nova `InputDefaultsParser`/`extract_input_defaults`),
  usando esse dicionário como base do payload, sobrescrito depois pelos campos que o
  CADE Monitor efetivamente controla (número do processo, checkboxes de tipo de busca etc.).
- **Rationale**: elimina a dependência de manter uma lista de campos ocultos hardcoded no código
  — se o SEI adicionar um campo novo (token anti-CSRF, campo de paginação etc.), ele é capturado
  automaticamente. É o mesmo padrão do Mesk (`InputDefaultsParser`, `extract_input_defaults`).
- **Alternatives considered**:
  - Continuar com o payload fixo e só atualizar manualmente quando quebrar — rejeitado, é
    exatamente o modo de falha que a User Story 3 descreve (manutenção reativa, app fora do ar
    até alguém notar).
  - Usar uma biblioteca de parsing de formulário HTML (ex. `lxml`, `BeautifulSoup`) — rejeitado,
    o projeto já tem um parser próprio baseado em `html.parser.HTMLParser` (Princípio I: stdlib
    preferida) e o caso de uso (ler `name`/`value` de `<input>`) é simples o suficiente para não
    justificar uma dependência nova (Princípio VIII).

## 3. Normalização do número do processo (zero a mais)

- **Decision**: nova função `normalize_cade_process_number(value)` que remove um zero extra no
  início do primeiro bloco de dígitos quando o restante do número bate com o formato
  `NNNNN.NNNNNN/NNNN-NN`, chamada antes de montar qualquer payload de busca.
- **Rationale**: mesmo fix já em produção no Mesk; erro de digitação comum e de baixo risco de
  corrigir (o padrão remanescente já precisa bater exatamente com o formato oficial do CADE).
- **Alternatives considered**:
  - Validar e rejeitar números com zero a mais, pedindo para o usuário corrigir — rejeitado,
    pior experiência sem ganho de segurança (a correção é determinística e sem ambiguidade).

## 4. Escolha do link certo quando a página cita mais de um processo

- **Decision**: `extract_process_detail_url` ganha um parâmetro opcional `process_number`. Quando
  informado, primeiro procura por um link de detalhe dentro de uma linha de tabela (`<tr>...</tr>`)
  cujo texto cite o número do processo pesquisado (comparação por dígitos, ignorando formatação);
  se não achar por linha, cai para o comportamento atual (primeiro link da página) apenas quando
  há exatamente um link candidato na página inteira e ele está associado à menção do processo.
- **Rationale**: a busca por texto livre/nº de documento (novas nesta feature) pode listar mais de
  um processo relacionado na mesma página de resultado; sem essa checagem, o sistema poderia
  resolver para o processo errado. Mesma ideia de `extract_process_detail_url` +
  `process_detail_url_near_reference` do Mesk, simplificada (sem a segunda passada de "contexto
  textual ±1000 caracteres" do Mesk, que não se mostrou necessária para os formatos de página já
  cobertos pelos testes existentes).
- **Alternatives considered**:
  - Sempre usar o primeiro link da página, como hoje — rejeitado, é seguro apenas quando a busca é
    por protocolo exato (praticamente garante um único resultado); deixa de ser seguro assim que
    as novas estratégias (texto/documento) entram em jogo.
  - Portar a lógica completa do Mesk (`process_detail_url_near_reference`, incluindo o fallback de
    proximidade textual) — considerado, mas adiado: aumenta a superfície de código sem um caso de
    teste real que hoje exija esse nível de refinamento; pode ser adicionado depois se aparecer um
    formato de página que a checagem por linha de tabela não cubra.

## 5. Compatibilidade com a interface pública existente

- **Decision**: `resolve_process_url`, `lookup_process_url` e `get_snapshot` mantêm a mesma
  assinatura e o mesmo contrato de retorno (`str | None`, exceções `FetchError`). Toda a mudança
  fica encapsulada dentro de `_resolve_process_detail`/`_build_search_payload_attempts` mais as
  novas funções em `extractors.py`.
- **Rationale**: `apps/telegram_bot/actions.py`, `apps/processes/services.py` e o management
  command `resolve_process.py` dependem dessas três funções; a spec (FR-005) exige não quebrar
  esses chamadores nem os testes que os mockam (`tests/test_telegram_actions.py`,
  `tests/test_telegram_latest.py`).

## 6. Correção pós-implementação: `partialfields` é obrigatório, não opcional

> Adicionado depois de validar a implementação ao vivo contra `sei.cade.gov.br` — registrado aqui
> por transparência, seguindo a convenção deste repositório de trazer para os documentos o que
> muda durante a implementação (ver README, seção sobre a feature 006).

Durante a validação manual (quickstart.md, passo 2), o payload de busca por protocolo **sem**
`partialfields` preenchido resolveu para um processo **errado** (`08700.009236/2026-73`, "Viagem:
Ao Exterior…") em vez do processo pesquisado (`08700.005905/2026-38`) — a página de resultado
mostrava "Exibindo 1 - 10 de 913263", ou seja, o SEI ignorou o filtro de protocolo e devolveu uma
listagem genérica de praticamente toda a base pública. Isso reproduz, ao vivo, exatamente o tipo de
falha silenciosa que esta feature existe para eliminar — e mostra que esse problema **já existe
hoje em produção** (o código anterior a esta feature também não define `partialfields`, e confiava
cegamente no primeiro link da página).

- **Decision revista**: `_build_search_payload_attempts` agora monta `partialfields` como
  `prot_pesq:*{dígitos_do_protocolo}* AND sta_prot:P` — a mesma consulta Solr que o Mesk usa em
  `fetch_cade_search_snapshot` — para todas as três estratégias de busca.
- **Por que a decisão original (seção 1) estava errada**: eu tinha descartado portar
  `partialfields` por avaliação estática do código, sem testar ao vivo primeiro. O teste ao vivo
  mostrou que, sem ele, o campo `txtProtocoloPesquisa` sozinho **não filtra** a busca no backend
  do SEI — ele só complementa a consulta Solr de `partialfields`. Corrigido antes de considerar a
  feature pronta.
- **Verificação**: com a correção, `lookup_process_url('08700.005905/2026-38', ...)` resolveu para
  exatamente a URL documentada no README do projeto (validada por humano), e o snapshot da página
  de detalhe contém o número do processo correto e "Lista de Protocolos".
