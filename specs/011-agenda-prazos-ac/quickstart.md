# Quickstart: validar prazos, convites e auto-encerramento de AC sumário

Pré-requisitos: ambiente configurado conforme o README, migrations aplicadas.

## 1. Rodar a suíte de testes automatizados (sem rede)

```powershell
python manage.py test apps.agenda
```

Resultado esperado: todos os testes passam, sem HTTP real, incluindo os 4 cenários isolados de
guarda de segurança do auto-encerramento (tasks.md).

## 2. Ver a linha do tempo de um AC sumário de exemplo, sem rede

```powershell
python manage.py shell -c "
from apps.agenda.deadlines import monta_linha_do_tempo
from apps.agenda.tests.fixtures import load_fixture
from apps.processes.models import MonitoredProcess
p = MonitoredProcess(last_text=load_fixture('ac_sumario_com_aprovacao.txt'))
for item in monta_linha_do_tempo(p):
    print(item)
"
```

Conferir manualmente: o prazo de análise da SG NÃO aparece (foi cumprido pela aprovação); o prazo
de recurso/avocação aparece calculado a partir da publicação da aprovação; a certidão aparece
como estimativa.

## 3. Validar manualmente contra a fonte real do calendário (opcional, 1-2 chamadas)

```powershell
python manage.py shell -c "
from apps.agenda.calendar_source import sync_calendar_year
sync_calendar_year(2027, timeout=15, user_agent='cade-monitor/1.0')
from apps.agenda.models import CadeCalendarYear
print(CadeCalendarYear.objects.get(year=2027).__dict__)
"
```

Confirmar que o ato oficial de 2027 é encontrado (ou que o sistema aceita normalmente não
encontrar, se ainda não publicado nesta época do ano) e que as datas batem com o que se espera.
Qualquer divergência do formato assumido deve virar uma seção "Correção pós-implementação" em
research.md, seguindo o modelo das features 008/009/010.

## 4. Confirmar que a classificação do processo bate com um processo AC sumário real

```powershell
python manage.py shell -c "
from apps.agenda.deadlines import classifica_processo
from apps.processes.models import MonitoredProcess
p = MonitoredProcess.objects.filter(label__icontains='sumário').first()  # ou um processo conhecido
print(classifica_processo(p.last_text) if p else 'nenhum processo AC sumário cadastrado para testar')
"
```

## 5. Testes de auto-encerramento (destrutivo — só em fixture/teste, nunca contra dado real)

```powershell
python manage.py test apps.agenda.tests.test_services -v 2 -k AutoClosure
```

Confirma isoladamente cada uma das 4 guardas de segurança de FR-017/FR-018.

## Critério de aceite da feature

- Passo 1 (testes automatizados) passa integralmente.
- Passo 2 produz uma linha do tempo correta para o cenário "já aprovado".
- Passo 3 confirma o formato real da fonte do calendário (ou gera a correção documentada).
- Passo 4 confirma a extração de classificação contra um processo real (ou documenta o ajuste
  necessário).
- Passo 5 confirma que nenhuma guarda de segurança do auto-encerramento pode ser contornada.
