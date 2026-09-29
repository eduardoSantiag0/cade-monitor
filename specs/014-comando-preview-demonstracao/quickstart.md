# Quickstart: validar o comando /preview

Pré-requisitos: ambiente já configurado (`./.venv/Scripts/python.exe manage.py migrate` — sem
migration nova nesta feature, mas garante o schema já existente).

## 1. Rodar a suíte de testes automatizados (com mock estrito de rede)

```powershell
./.venv/Scripts/python.exe manage.py test apps.telegram_bot.tests.test_demo -v 2
```

Resultado esperado: todos os testes passam, incluindo o teste que falha propositalmente se
qualquer função de rede (`urllib.request.urlopen` e afins) for chamada durante `RunDemoUseCase.run()`
(prova de FR-006/SC-002).

## 2. Ver a resposta do `/preview` sem subir o bot de verdade

```powershell
./.venv/Scripts/python.exe manage.py shell -c "
from apps.telegram_bot.demo import RunDemoUseCase
print(RunDemoUseCase().run())
"
```

Conferir manualmente: a resposta tem processo fictício, andamento anterior, nova movimentação,
data/hora, resumo, e os canais de notificação — tudo em português legível.

## 3. Confirmar idempotência (não acumula registros)

```powershell
./.venv/Scripts/python.exe manage.py shell -c "
from apps.processes.models import MonitoredProcess
from apps.monitoring.models import DetectedChange
from apps.telegram_bot.demo import RunDemoUseCase, DEMO_PROCESS_SOURCE

for _ in range(5):
    RunDemoUseCase().run()

print('Processos fictícios:', MonitoredProcess.objects.filter(source=DEMO_PROCESS_SOURCE).count())
print('Mudanças de demonstração:', DetectedChange.objects.filter(process__source=DEMO_PROCESS_SOURCE).count())
"
```

Resultado esperado: 1 processo, 1 mudança — mesmo depois de 5 execuções seguidas.

## 4. Confirmar que dados reais não são tocados

```powershell
./.venv/Scripts/python.exe manage.py test apps.telegram_bot -v 1
```

Roda toda a suíte do app (incluindo os comandos reais já existentes) junto com a nova — confirma
que nada foi quebrado nos comandos reais.

## Critério de aceite da feature

- Passo 1 passa integralmente, incluindo a prova estrita de "sem rede".
- Passo 2 produz uma resposta legível com todos os elementos exigidos por FR-009.
- Passo 3 confirma idempotência (SC-004).
- Passo 4 confirma que a feature não quebrou nada do bot já existente.
