# Data Model: Comando /preview — demonstração para portfólio

Nenhum modelo novo. A feature reaproveita, sem alteração de schema:

## `apps.processes.models.MonitoredProcess` (existente)

Um único registro reservado, identificado por um `source` constante e reconhecível como fictício
(`DEMO_PROCESS_SOURCE = '08700.000000/2026-00'`, em `apps/telegram_bot/demo.py`). Sempre
`status=ProcessStatus.ARCHIVED` (nunca entra no ciclo de `get_due_processes`). `label` com um
prefixo claro de demonstração (ex. `'[Demonstração] Ato de Concentração fictício'`).

## `apps.monitoring.models.CheckRun` / `PageSnapshot` / `DetectedChange` (existentes)

Um conjunto reservado (mesmo padrão get-or-create), ligado ao `MonitoredProcess` de demonstração,
recriado/atualizado no lugar a cada execução de `/preview` (nunca acumula um novo conjunto por
chamada — ver research.md).

## Relação

```text
MonitoredProcess (demo, único, status=ARCHIVED)
  └── CheckRun (demo, único)
        └── PageSnapshot (demo, único)
        └── DetectedChange (demo, único)
```

Sem nenhuma `ProcessSubscription`/`Notification` real criada — o conteúdo de exemplo de
notificação é gerado por `build_test_notification_body` (função pura, sem persistência) e exibido
direto na resposta do `/preview`, nunca persistido como uma notificação pendente. Ver
[contracts/preview.md](contracts/preview.md) para o contrato completo.
