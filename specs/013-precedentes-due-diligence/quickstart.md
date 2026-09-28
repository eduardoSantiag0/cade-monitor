# Quickstart: validar a fundação de Precedentes

Pré-requisitos: ambiente já configurado (`./.venv/Scripts/python.exe manage.py migrate`).

## 1. Rodar a suíte de testes automatizados (sem rede — não há nenhuma chamada externa nesta spec)

```powershell
./.venv/Scripts/python.exe manage.py test apps.precedentes
```

Resultado esperado: todos os testes passam, cobrindo as 4 histórias de usuário e as regras de
negócio (FR-004 a FR-012) diretamente, sem fixture de HTTP (não há rede nesta feature).

## 2. Fluxo manual de ponta a ponta (via shell, sem UI)

```powershell
./.venv/Scripts/python.exe manage.py shell -c "
from django.contrib.auth.models import User
from apps.precedentes import services

user = User.objects.first()
case = services.create_case(user, 'Aquisição X por Y', cliente='Cliente Exemplo')
entity = services.add_entity(case, 'requerente', 'Empresa Exemplo LTDA', cnpj='00.000.000/0001-00')

fact = services.record_fact(
    entity, user, campo='faturamento', valor='R\$ 500 milhões',
    status='confirmado', fonte_descricao='Demonstrações financeiras 2025',
)
print('Fato criado:', fact.pk, fact.valor)

corrected = services.correct_fact(fact, user, motivo='Valor revisado após novo balanço', valor='R\$ 520 milhões')
print('Corrigido:', corrected.pk, corrected.valor, 'raiz:', corrected.root_id or corrected.pk)

from apps.precedentes import selectors
history = list(selectors.fact_history(corrected))
print('Histórico:', [(h.pk, h.valor, h.is_current) for h in history])

analysis = services.record_analysis(case, user, 'Faturamento sugere porte relevante para overlap.', [fact])
print('Análise:', analysis.pk, 'fatos-base:', [f.pk for f in analysis.facts.all()])
"
```

Conferir manualmente: o histórico mostra as 2 versões (original + corrigida), só a corrigida com
`is_current=True`; a análise referencia a linha-raiz do fato, não a versão corrigida.

## 3. Validar a rejeição de confirmado-sem-fonte e correção-sem-motivo

```powershell
./.venv/Scripts/python.exe manage.py test apps.precedentes.tests.test_services -v 2
```

## Critério de aceite da feature

- Passo 1 (testes automatizados) passa integralmente.
- Passo 2 confirma o fluxo completo (caso → empresa → fato → correção → histórico → análise)
  funcionando via `services.py`, sem UI.
- Passo 3 confirma que FR-004 e FR-007 realmente bloqueiam entrada inválida.
