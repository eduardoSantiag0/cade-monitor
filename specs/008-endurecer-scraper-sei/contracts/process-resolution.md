# Contrato: resolução de processo CADE/SEI (`apps/monitoring`)

Este módulo é interno ao monolito (sem API HTTP própria), mas tem consumidores internos claros —
`apps/telegram_bot/actions.py`, `apps/processes/services.py` e
`management/commands/resolve_process.py`. Este documento fixa o contrato que esses consumidores
podem continuar assumindo depois desta feature.

## Funções públicas (`apps/monitoring/clients.py`) — inalteradas na assinatura

### `resolve_process_url(process_number: str, timeout: int, user_agent: str) -> str | None`

- **Entrada**: número de processo em qualquer formatação aceita hoje (com ou sem um zero a mais
  no início do primeiro bloco).
- **Saída**:
  - URL pública de detalhe (`str`) quando alguma das três estratégias de busca encontrar o
    processo.
  - `None` quando nenhuma estratégia encontrar link (processo inexistente ou não público) **ou**
    quando ocorrer uma falha de acesso (`FetchError`) — mesmo comportamento de hoje, engolindo o
    erro.
- **Não muda**: chamadores que já tratam `None` como "não encontrado" continuam funcionando sem
  qualquer ajuste.

### `lookup_process_url(process_number: str, timeout: int, user_agent: str) -> str | None`

- Mesma entrada/saída de sucesso que `resolve_process_url`, mas **propaga** `FetchError` em vez de
  engolir — usado pelo bot do Telegram para diferenciar "processo não encontrado" (retorna `None`)
  de "falha de rede, vale tentar de novo" (levanta `FetchError`).
- **Novidade interna**: agora pode fazer até 4 requisições HTTP antes de decidir (1 GET dos
  defaults do formulário + até 3 POSTs), todas sequenciais, todas sujeitas à mesma política de
  retry/backoff por requisição já existente. Se qualquer uma delas falhar de forma não recuperável,
  a exceção `FetchError` sobe imediatamente (não tenta as estratégias restantes) — mesma política
  de "erro de rede não é silenciado" de hoje.

### `get_snapshot(source: str, timeout: int, user_agent: str) -> Snapshot`

- Sem mudança de contrato. Quando `source` é um número de processo (não uma URL), delega para o
  mesmo caminho reforçado de `_fetch_by_process_number`.

## Funções internas novas/alteradas (`apps/monitoring/extractors.py`)

Não fazem parte da API pública do app, mas ficam documentadas aqui por serem o núcleo da mudança
e por serem exercitadas diretamente pelos testes (fixtures HTML locais, Princípio VII).

### `extract_input_defaults(html: str) -> dict[str, str]` (nova)

- **Entrada**: HTML de uma página com um `<form>`.
- **Saída**: dicionário `name -> value` de cada `<input>` encontrado (last-write-wins na ordem do
  documento). HTML sem `<input>` → dicionário vazio, nunca lança exceção.

### `normalize_cade_process_number(value: str) -> str` (nova)

- **Entrada**: string de número de processo, possivelmente com um zero a mais no início.
- **Saída**: mesma string, com o zero extra removido **somente** quando o restante já bate com o
  formato `NNNNN.NNNNNN/NNNN-NN`; caso contrário, devolve a string original sem alteração (nunca
  lança exceção, nunca "adivinha" um formato inválido).

### `extract_process_detail_url(html: str, process_number: str | None = None) -> str | None` (parâmetro novo, opcional)

- **Compatibilidade**: chamada sem `process_number` (assinatura antiga) continua se comportando
  exatamente como hoje — primeiro link de detalhe encontrado na página.
- **Novo comportamento com `process_number`**: prioriza o link cuja linha de tabela cite o número
  do processo pesquisado; só recorre ao "primeiro link da página" quando há exatamente um link
  candidato e a página como um todo cita o processo pesquisado.
- **Saída**: `None` quando não há link algum, ou quando há mais de um link candidato e nenhum
  deles está associado ao processo pesquisado (evita resolver para o processo errado).

## Garantias que os testes existentes continuam exercitando

- `tests/test_monitoring.py`: extração de protocolos/andamentos/hash — não afetado por esta
  feature, deve continuar passando sem alteração.
- `tests/test_telegram_actions.py`, `tests/test_telegram_latest.py`: mockam `lookup_process_url`
  diretamente (não o HTTP por baixo), então continuam válidos sem alteração — o contrato de
  entrada/saída dessa função é o que este documento fixa.
