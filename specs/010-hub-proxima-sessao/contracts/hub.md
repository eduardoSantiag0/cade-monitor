# Contrato: `apps/dashboard/hub.py`

Módulo interno ao monolito (sem API HTTP própria). Dois consumidores: a view do dashboard (leitura
só) e `run_worker._run_cycle` (escrita, via refresh).

## Leitura (consumida por `apps/dashboard/views.py::index`)

### `proxima_sessao() -> dict | None`

- Lê `cache.get('hub:sessoes')`; filtra pela data de hoje em diante; devolve a mais próxima
  (`{'data': date, 'titulo': str}`) ou `None` quando não há cache ou não há sessão futura nele.
- **Nunca faz HTTP.** Sempre retorna rápido (leitura de cache).

### `pauta_url(sessao: dict) -> str`

- Extrai `{ano, numero}` do título/data de `sessao` (mesmo padrão de `\d+ª`); lê
  `cache.get(f'hub:pauta:{ano}:{numero}')`; devolve a URL ou `''`.
- **Nunca faz HTTP.**

## Escrita (consumida por `run_worker._run_cycle`)

### `refresh_sessoes(timeout: int, user_agent: str) -> None`

- Gate de cadência (`hub:last_attempt:sessoes`, mesmo espírito de `DouFetchState`/`_should_fetch`
  da feature 009) — se dentro do intervalo mínimo, não faz HTTP.
- Busca `https://www.gov.br/cade/pt-br/assuntos/sessoes/calendario-de-sessoes`, faz parsing
  (`sessoes_do_html`) e grava em `cache.set('hub:sessoes', ..., timeout=7*24*3600)`
  em sucesso. Falha de rede/parsing: loga e retorna sem gravar (cache anterior, se houver,
  continua valendo até expirar) — nunca lança exceção para o chamador.

### `refresh_pauta(timeout: int, user_agent: str) -> None`

- Só roda depois de `proxima_sessao()` já ter algo no cache (sem sessão futura conhecida, não há
  o que buscar). Mesmo gate de cadência (`hub:last_attempt:pauta`).
- Busca a página anual de pautas do CADE para o ano/número da sessão corrente, extrai o link do
  PDF (`pauta_do_html`) e grava em `cache.set(f'hub:pauta:{ano}:{numero}', url,
  timeout=...)` — TTL de 7 dias se achou, 6 horas se não achou (retenta mais cedo, a pauta pode
  sair a qualquer momento). Nunca lança exceção para o chamador.

## `apps/monitoring/management/commands/run_worker.py` — ponto de integração

`_run_cycle()` ganha uma chamada, no mesmo bloco/padrão das chamadas `run_*_window` da feature 009
(try/except + log, nunca interrompe o ciclo):

```python
from apps.dashboard.hub import refresh_pauta, refresh_sessoes
try:
    refresh_sessoes(settings.REQUEST_TIMEOUT_SECONDS, settings.USER_AGENT)
    refresh_pauta(settings.REQUEST_TIMEOUT_SECONDS, settings.USER_AGENT)
except Exception as exc:
    logger.error(...); sentry_sdk.capture_exception(exc)
```
