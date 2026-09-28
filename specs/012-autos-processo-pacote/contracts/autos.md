# Contrato: `apps/autos` — funções e views

## `apps/autos/services.py`

### `request_package(process: MonitoredProcess, user: User) -> AutosPackageJob`

- FR-005: se já existe um `AutosPackageJob` de `process` com `status in ('queued', 'processing')`,
  ou `status='ready'` e `expires_at` no futuro, devolve esse job (não cria um novo). Caso
  contrário, cria um novo com `status='queued'`.

### `run_pending_packages(now: datetime) -> dict`

- Chamada pelo `run_worker`: processa **um** job `queued` por ciclo (o mais antigo), evitando que
  um único ciclo do worker fique preso indefinidamente montando um pacote gigante enquanto ignora
  o resto do trabalho do ciclo — o job avança incrementalmente por chamadas sucessivas do worker,
  não tudo de uma vez. Marca `status='processing'` ao pegar o job; chama `builder.monta_pacote`.
  Nunca lança exceção para o chamador — falha inesperada vira `status='failed'` com o erro
  registrado, não uma exceção não tratada subindo até `run_worker`.
- Também remove arquivos de jobs `ready` com `expires_at` no passado (FR-011), marcando-os como
  expirados (reaproveita `status='failed'` ou um valor `expired` — decisão de implementação, ver
  tasks.md).

## `apps/autos/builder.py`

### `monta_pacote(job: AutosPackageJob, timeout: int, user_agent: str) -> None`

- Busca a página fresca do processo (`get_snapshot`), extrai `extract_protocol_records` (lista
  declarada) e `extract_document_links` (URLs). Grava `job.total_declared`.
- Para cada registro, nessa ordem: se há URL, tenta baixar via `download_document`. Sucesso →
  escreve a entrada numerada real no ZIP. **Sem URL, OU com URL mas o download falhou** (rede,
  HTTP, timeout — mesma regra para os dois casos, spec.md Edge Cases), procura corroboração no
  andamento/página (research.md): achando, escreve um `.txt` numerado com o motivo; não achando,
  registra uma divergência (nenhuma entrada escrita nessa posição). Como todo registro declarado
  vira exatamente uma das três coisas (entrada real, placeholder, ou divergência), a checagem final
  é simplesmente "nenhuma divergência registrada" — não uma comparação de contagens separada.
- `time.sleep(settings.SLEEP_BETWEEN_REQUESTS_SECONDS)` entre cada documento.
- Ao final: se todas as posições viraram entrada real ou placeholder corroborado (nenhuma
  divergência), fecha o ZIP, grava `job.file_path`, `job.status='ready'`,
  `job.expires_at=now+AUTOS_PACKAGE_TTL_SECONDS`. Havendo qualquer divergência, descarta o arquivo
  parcial (nunca fica em `MEDIA_ROOT` acessível), grava `job.status='failed'` com uma mensagem
  citando quantos documentos divergiram.
- Nunca lança exceção para o chamador (`run_pending_packages` trata qualquer falha inesperada
  como `status='failed'` também, mas o caminho normal de "divergência" não é uma exceção — é um
  resultado esperado e tratado).

## `apps/autos/selectors.py`

### `active_or_recent_job(process) -> AutosPackageJob | None`

- Usado por `request_package` (services.py) e pela view de status — mesma query, sem duplicar.

## `apps/autos/views.py` (autenticadas, `@login_required`)

### `POST /processes/<pk>/autos/pedir/`

- Chama `request_package`, redireciona de volta para a página do processo (o status aparece na
  seção "Autos" do template, FR-001/FR-002).

### `GET /processes/<pk>/autos/status/` (opcional — pode ser só parte do contexto de `process_detail`)

- Devolve o job ativo/mais recente (ou nenhum) para renderizar o status na página do processo —
  provavelmente implementado como parte do contexto de `apps/processes/views.py::process_detail`
  em vez de uma rota separada, decisão de tasks.md.

### `GET /processes/<pk>/autos/baixar/<job_id>/`

- Só serve o arquivo (`FileResponse`) quando `job.status='ready'` e `job.expires_at` no futuro;
  qualquer outro caso, 404 (não expõe se o job existe/não existe a quem não tem acesso — mesmo
  padrão de "não vazar existência" já esperado em views autenticadas deste projeto).

## `apps/monitoring/management/commands/run_worker.py` — ponto de integração

Mesmo padrão das features 009/010/011, em `_run_cycle()`:

```python
from apps.autos.services import run_pending_packages
try:
    run_pending_packages(timezone.now())
except Exception as exc:
    logger.error('[worker] Erro em run_pending_packages: %s', exc, exc_info=True)
    sentry_sdk.capture_exception(exc)
```

Posição no ciclo: não depende de nenhuma outra feature (dou/agenda) nem é dependência delas — pode
entrar em qualquer ponto do bloco de passos "extra" do `_run_cycle`, depois dos passos já
existentes de monitoramento de processo.
