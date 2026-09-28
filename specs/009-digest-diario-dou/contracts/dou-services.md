# Contrato: `apps/dou` — funções chamadas pelo `run_worker`

App interno ao monolito (sem API HTTP própria). Este documento fixa o contrato entre
`apps/dou/services.py` e o único consumidor externo ao app: `run_worker._run_cycle()`.

## `apps/dou/services.py`

### `run_digest_window(now: datetime) -> dict`

- **Quando chamar**: a cada tick do worker, sempre — a função decide internamente se está dentro
  da janela diária configurada (`DOU_DIGEST_WINDOW_START` / `_END`) e se já não passou o intervalo
  mínimo de 5 min desde a última tentativa (`DouFetchState[source='resenha'|'ingov_listing']`).
  Fora da janela ou dentro do intervalo mínimo: retorna imediatamente sem HTTP (`{'skipped': True}`).
- **Comportamento dentro da janela**: busca a Resenha do dia; se indisponível, tenta a listagem do
  in.gov.br; monta o digest (mesmo conteúdo para todos, destaque calculado por assinante); para
  cada `DouSubscription` com `enabled=True` e `subscriber.is_reachable()`, envia exatamente um
  e-mail de `kind='digest'` para `reference_date=hoje`, salvo se já existir `DouSendLog` para essa
  combinação (idempotente — pode ser chamado várias vezes no mesmo dia sem duplicar envio).
- **Saída**: `{'skipped': bool, 'sent': int, 'failed': int}` — usado só para log (`run_worker` não
  toma decisão com base nisso).
- **Nunca lança exceção** para o chamador: falhas de rede/parsing/envio são capturadas, logadas e
  contam em `failed`; uma falha em um assinante não impede o envio aos demais.

### `run_anticipation_window(now: datetime) -> dict`

- Mesmo formato de retorno e mesma garantia de não lançar exceção.
- Age apenas sobre `DouSubscription` com `nextday_enabled=True`; horário de disparo é o
  `nextday_time` de cada assinante (não uma janela global única) — a função é chamada a cada tick
  e decide, por assinante, se `now` já passou do horário configurado e ainda não há
  `DouSendLog(kind='pubdou_ant', reference_date=amanhã)` para ele.
- Repete a checagem até um horário-limite da noite (`DOU_ANTICIPATION_CUTOFF`); itens novos desde
  o envio anterior viram um envio `kind='pubdou_compl'` (nunca repete item já enviado).

### `run_confirmation_window(now: datetime) -> dict`

- Mesmo formato de retorno e mesma garantia de não lançar exceção.
- Age sobre `DouSubscription` com `nextday_enabled=True` que tenham uma `DouAnticipation` para a
  data de hoje; busca o DOU real do dia (mesma fonte/cadência de `run_digest_window`, mas cada
  fonte tem seu próprio `DouFetchState`, então não compete pelo mesmo marcador de 5 min do
  digest) e envia `kind='pubdou_conf'` comparando antecipado × publicado.

## `apps/monitoring/management/commands/run_worker.py` — ponto de integração

`_run_cycle()` ganha, entre o passo 2 (processos vencidos) e o passo 3 (notificações pendentes),
três chamadas na mesma forma dos blocos já existentes (try/except + `sentry_sdk.capture_exception`
+ log, nunca interrompendo o ciclo):

```python
from apps.dou.services import (
    run_digest_window, run_anticipation_window, run_confirmation_window,
)
for step in (run_digest_window, run_anticipation_window, run_confirmation_window):
    try:
        step(timezone.now())
    except Exception as exc:
        logger.error(...); sentry_sdk.capture_exception(exc)
```

## Funções auxiliares (internas, exercitadas diretamente pelos testes)

### `apps/dou/clients.py`

- `fetch_resenha(date: date, timeout: int, user_agent: str) -> dict | None` — `None` quando a
  Resenha do dia ainda não está disponível (não é erro); levanta `FetchError` em falha de rede.
- `fetch_ingov_listing(date: date, timeout: int, user_agent: str) -> dict` — sempre retorna um
  dict (`{'editais': [...], 'despachos': [...], 'atas': [...]}`, possivelmente todas vazias);
  levanta `FetchError` em falha de rede.

### `apps/dou/render.py`

- `render_digest_text(dou_data: dict, terms: list[str]) -> str`
- `render_digest_html(dou_data: dict, terms: list[str]) -> str`
- `render_confirmation_text/html(anticipated: list[dict], published: dict) -> str`

Mesma assinatura de entrada/saída independente da fonte de onde `dou_data` veio (Resenha ou
in.gov.br) — `clients.py`/`parsers.py` normalizam para o mesmo formato de dict antes de chegar em
`render.py`, então o motor de formatação não sabe (nem precisa saber) qual fonte respondeu.
