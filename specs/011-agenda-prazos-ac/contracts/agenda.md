# Contrato: `apps/agenda` — funções chamadas pelo `run_worker` e pela view do processo

App interno ao monolito (sem API HTTP própria). Consumidores: `run_worker._run_cycle()` (escrita)
e `apps/processes/views.py::detail` (leitura, linha do tempo).

## `apps/agenda/calendar_source.py`

### `sync_calendar_year(year: int, timeout: int, user_agent: str) -> None`

- Gate de cadência via `CadeCalendarYear.next_check_at` (FR-003). Busca o ato oficial na listagem
  do DOU, valida (FR-002), grava `CadeCalendarYear`/`CadeCalendarEntry` em sucesso. Nunca lança
  exceção para o chamador — falha vira log + `next_check_at` reagendado.

### `is_business_day(day: date) -> bool`

- Lê `CadeCalendarEntry` do ano de `day` (mais fim de semana) — `True` quando não é fim de semana
  nem feriado/ponto facultativo confirmado. Quando o ano não está confirmado, o chamador
  (`deadlines.py`) decide o que fazer (FR-011) — esta função só responde com o que sabe.

## `apps/agenda/deadlines.py`

### `calcula_prazo_cade(data_evento: date, dias: int) -> date`

- Fórmula de FR-004 (ver research.md). Levanta `CalendarNotConfirmedError` quando o ano
  necessário não está confirmado — o chamador trata isso como "prazo pendente", nunca como erro
  fatal (FR-011).

### `classifica_processo(last_text: str) -> str | None`

- `'ac_sumario'` quando a classificação bate com Ato de Concentração Sumário; `None` para
  qualquer outra coisa (inclusive as classificações da lista de exclusão de FR-005).

### `monta_linha_do_tempo(process: MonitoredProcess) -> list[dict]`

- `None` (lista vazia) quando `classifica_processo` não é `'ac_sumario'`.
- Caso contrário: identifica os documentos (notificação, edital, publicação, aprovação, certidão)
  via `extract_protocol_records(process.last_text)`, cada um com `confidence` (FR-006); calcula os
  4 prazos (FR-007 a FR-010), omitindo os que dependem de um documento ainda não encontrado ou de
  um ano de calendário não confirmado. Cada item: `{'tipo', 'vencimento', 'estimado': bool,
  'confidence': float}`. Nunca lança exceção — documento ambíguo vira item omitido ou com
  confiança baixa, nunca uma adivinhação silenciosa.

## `apps/agenda/ics.py`

### `build_ics(uid: str, sequence: int, method: str, summary: str, event_date: date) -> bytes`

- `method` ∈ `'REQUEST'`, `'CANCEL'`. Gera o `.ics` mínimo (evento de dia inteiro, RFC 5545,
  dobra de linha em 75 octetos) — ver research.md para os campos replicados do Mesk.

## `apps/agenda/services.py`

### `sync_calendar(now: datetime) -> None`

- Chama `sync_calendar_year` para o ano corrente e o seguinte (cobre a virada de ano — FR-003).
  Nunca lança exceção.

### `refresh_timelines_and_invites(now: datetime) -> dict`

- Para cada `MonitoredProcess` ativo classificado como AC sumário: `monta_linha_do_tempo`; para
  os 2 tipos de prazo com convite (`sg_analysis`, `final_certificate`, FR-012), compara com
  `ProcessInvite` existente — sem registro → envia REQUEST (T novo); data mudou → envia REQUEST
  com `sequence+1` (FR-015); prazo sumiu do resultado da linha do tempo → envia CANCEL (FR-016);
  sem mudança → não faz nada (FR-014). Envia só a assinantes com e-mail habilitado e não pausado
  (`ProcessSubscription`, FR-013). Nunca lança exceção para o chamador — falha por processo é
  logada e não interrompe os demais.

### `run_auto_closure(now: datetime) -> dict`

- Para cada `MonitoredProcess` ativo classificado como AC sumário com uma certidão de confiança
  alta na linha do tempo: avalia as 4 condições de FR-017 (certidão de confiança alta; ≥10 dias
  sem movimentação desde a certidão ou desde a última `DetectedChange` posterior a ela, o que for
  mais recente; `last_error` vazio; `last_checked_at` há no máximo 2 dias). Todas as 4 → envia
  CANCEL de qualquer `ProcessInvite` pendente (FR-019), loga os critérios (FR-020), apaga o
  processo (cascata já cobre assinaturas/documentos ligados). Qualquer condição ausente → não faz
  nada, sem log de erro (é o caminho normal, não uma falha). Nunca lança exceção para o chamador.

## `apps/monitoring/management/commands/run_worker.py` — ponto de integração

Mesmo padrão das features 009/010, em `_run_cycle()`:

```python
from apps.agenda.services import run_auto_closure, refresh_timelines_and_invites, sync_calendar
for agenda_step in (sync_calendar, refresh_timelines_and_invites, run_auto_closure):
    try:
        agenda_step(timezone.now())
    except Exception as exc:
        logger.error('[worker] Erro em %s: %s', agenda_step.__name__, exc, exc_info=True)
        sentry_sdk.capture_exception(exc)
```

Ordem importa: `sync_calendar` antes de `refresh_timelines_and_invites` (precisa do calendário do
ano); `refresh_timelines_and_invites` antes de `run_auto_closure` (cancela convite antes de
apagar, FR-019).

## Leitura (consumida por `apps/processes/views.py::detail`)

### `apps/agenda/selectors.py::timeline_for_process(process) -> list[dict] | None`

- Wrapper fino sobre `deadlines.monta_linha_do_tempo`, para a view não importar direto de dentro
  do app (mesmo padrão de `selectors.py` nas features anteriores). `None` quando o processo não é
  AC sumário (a view não renderiza a seção).
