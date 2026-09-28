# Data Model: Agenda e prazos de AC sumário

Todos os modelos novos vivem em `apps/agenda/models.py`. Nenhum modelo existente
(`MonitoredProcess`, `ProcessSubscription`, `DetectedChange`) é alterado — apenas lido.

## `CadeCalendarYear`

Um registro por ano-calendário, com o status da sincronização.

| Campo | Tipo | Notas |
|---|---|---|
| `year` | `PositiveIntegerField(unique=True)` | Ano civil |
| `status` | `CharField(choices)` | `pending` (não confirmado), `confirmed`, `conflict` (retificação encontrada) |
| `official_act` | `CharField(blank=True)` | Identificação da Portaria (nº/ano) quando confirmado |
| `official_source_url` | `URLField(blank=True)` | Link do DOU onde o ato foi encontrado |
| `last_checked_at` | `DateTimeField(null=True)` | Última tentativa de sincronização |
| `next_check_at` | `DateTimeField(null=True)` | Próxima tentativa permitida (implementa a cadência de FR-003) |

## `CadeCalendarEntry`

Um registro por dia não útil de um ano.

| Campo | Tipo | Notas |
|---|---|---|
| `calendar_year` | FK → `CadeCalendarYear` | `related_name='entries'` |
| `date` | `DateField` | Dia não útil |
| `name` | `CharField` | Nome do feriado/ponto facultativo |

Restrição: `unique_together = ('calendar_year', 'date')`.

## `ProcessInvite`

Um registro por (processo, tipo de prazo) — o que já foi enviado como convite de calendário.

| Campo | Tipo | Notas |
|---|---|---|
| `process` | FK → `processes.MonitoredProcess` | `related_name='agenda_invites'`, `on_delete=CASCADE` |
| `deadline_type` | `CharField(choices)` | `sg_analysis` ou `final_certificate` (só os dois com convite, FR-012) |
| `uid` | `CharField` | Identificador estável do compromisso (`ac-{process_id}-{deadline_type}@cade-monitor`) |
| `event_date` | `DateField` | Última data enviada |
| `sequence` | `PositiveIntegerField(default=0)` | Incrementado a cada atualização (FR-015) |
| `status` | `CharField(choices)` | `sent`, `cancelled` |
| `is_estimate` | `BooleanField` | Se a última data enviada era estimativa (certidão prevista) ou real |
| `updated_at` | `DateTimeField(auto_now=True)` | |

Restrição: `unique_together = ('process', 'deadline_type')` — é a chave que permite decidir
reenviar (data mudou), cancelar (prazo sumiu) ou não fazer nada (idempotência, FR-014).

## Relação com entidades existentes

```text
MonitoredProcess (existente) 1───N ProcessInvite

CadeCalendarYear 1───N CadeCalendarEntry   (sem relação com MonitoredProcess — é global)
```

A linha do tempo de prazos (`deadlines.py::monta_linha_do_tempo`, ver contracts/agenda.md) **não**
é um modelo — é sempre recalculada em memória, a partir de:
- `MonitoredProcess.last_text` → `apps/monitoring/extractors.py::extract_protocol_records`
  (documentos)
- `CadeCalendarYear`/`CadeCalendarEntry` do(s) ano(s) relevante(s) (calendário)

Ver [contracts/agenda.md](contracts/agenda.md) para o contrato completo das funções.
