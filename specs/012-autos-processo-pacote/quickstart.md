# Quickstart: validar o pacote de autos

Pré-requisitos: ambiente já configurado (`python manage.py migrate`).

## 1. Rodar a suíte de testes automatizados (sem rede)

```powershell
./.venv/Scripts/python.exe manage.py test apps.autos apps.monitoring apps.processes
```

Resultado esperado: todos os testes passam, sem nenhuma chamada HTTP real (fixtures locais,
Princípio VII), sem escrever fora de um diretório temporário de teste.

## 2. Ver um pacote de exemplo sem HTTP real

```powershell
./.venv/Scripts/python.exe manage.py shell -c "
from apps.autos.tests.fixtures import load_fixture
from apps.monitoring.extractors import extract_protocol_records
records = extract_protocol_records(load_fixture('processo_com_documentos.txt'))
print(len(records), 'documentos declarados')
"
```

## 3. Validar manualmente contra um processo público real (opcional, econômico)

```powershell
./.venv/Scripts/python.exe manage.py shell -c "
from apps.monitoring.clients import get_snapshot, extract_document_links
from apps.monitoring.extractors import extract_protocol_records
snap = get_snapshot('<URL pública de um processo conhecido>', 15, 'cade-monitor/1.0')
records = extract_protocol_records(snap.text)
links = extract_document_links(snap.html, snap.url)
print(len(records), 'declarados;', len(links), 'com link encontrado')
"
```

Cenário para conferir uma única vez: confirmar que `extract_document_links` sobre o HTML fresco
encontra URLs para a maioria dos documentos declarados (documentos sem link são esperados — são
os candidatos a placeholder/divergência).

## 4. Ponta a ponta (job simulado)

```powershell
./.venv/Scripts/python.exe manage.py test apps.autos.tests.test_builder apps.autos.tests.test_services -v 2
```

Cobre: caminho feliz (todos os documentos com link), placeholder corroborado, divergência
(job falha, nenhum arquivo disponível), e "um job por vez por processo".

## Critério de aceite da feature

- Passo 1 passa integralmente.
- Passo 3 confirma que a extração de links funciona contra pelo menos um processo real.
- Passo 4 cobre os três desfechos (pronto / placeholder / falha por integridade) com fixtures.
