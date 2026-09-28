# Data Model: Pacote de autos (documentos públicos) do processo

Um único modelo novo em `apps/autos/models.py`. Nenhum modelo existente (`MonitoredProcess`,
`DetectedDocument`) é alterado.

## `AutosPackageJob`

Um registro por pedido de montagem — funciona como fila (consumida pelo `run_worker`) e como
registro do resultado (para a view de status/download).

| Campo | Tipo | Notas |
|---|---|---|
| `process` | FK → `processes.MonitoredProcess` | `on_delete=CASCADE`, `related_name='autos_jobs'` |
| `requested_by` | FK → `auth.User` | Quem pediu (para auditoria; a autorização de download é "autenticado", não por dono) |
| `status` | `CharField(choices)` | `queued`, `processing`, `ready`, `failed`, `expired` |
| `total_declared` | `PositiveIntegerField(null=True)` | Nº de documentos que a Lista de Protocolos declara — preenchido ao iniciar o processamento |
| `total_processed` | `PositiveIntegerField(default=0)` | Nº de entradas já escritas no ZIP (real ou placeholder) — avança durante o processamento |
| `plan` | `JSONField(default=list)` | **(desvio deste documento, ver tasks.md "Desvios")** Plano de documentos (URL/motivo já resolvidos), montado uma única vez na primeira chamada de `monta_pacote` — permite retomar entre ciclos do worker sem refazer o fetch/extração. |
| `next_index` | `PositiveIntegerField(default=0)` | Próximo item do `plan` a processar — o cursor de retomada entre chamadas. |
| `divergences` | `JSONField(default=list)` | Documentos sem link e sem corroboração, acumulados durante o processamento — usado para compor `error` ao final. |
| `file_path` | `CharField(blank=True)` | Caminho relativo em `MEDIA_ROOT` do ZIP pronto (vazio até `status='ready'`) |
| `error` | `TextField(blank=True)` | Mensagem legível quando `status='failed'` (ex.: divergência declarado×processado) |
| `expires_at` | `DateTimeField(null=True)` | Quando o arquivo pronto deve ser removido (`AUTOS_PACKAGE_TTL_SECONDS` após ficar pronto) |
| `created_at` / `updated_at` | `DateTimeField` | Auditoria padrão do projeto |

Sem `unique_together` explícito — a garantia de "não duplicar job em andamento para o mesmo
processo" (FR-005) é lógica de `services.py::request_package` (busca um job `queued`/`processing`
não expirado antes de criar um novo), não uma constraint de banco, porque um job `failed`/`ready`
antigo do mesmo processo é um registro histórico legítimo, não um conflito.

## Relação com entidades existentes

```text
MonitoredProcess (existente) 1───N AutosPackageJob
auth.User (existente)        1───N AutosPackageJob
```

Nenhuma outra entidade/tabela nova: o plano de documentos vive dentro do próprio
`AutosPackageJob.plan` (campo `plan` acima), montado uma única vez a partir do fetch fresco da
página (research.md) — não uma tabela relacional própria. Ver [contracts/autos.md](contracts/autos.md)
para o contrato das funções.
