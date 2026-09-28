# Quickstart: validar o digest diário do DOU

Pré-requisitos: ambiente já configurado conforme o README do projeto (`.venv` com
`requirements.txt` instalado, migrations aplicadas: `python manage.py migrate`).

## 1. Rodar a suíte de testes automatizados (sem rede)

```powershell
python manage.py test apps.dou apps.monitoring
```

Resultado esperado: todos os testes passam, incluindo os novos casos desta feature (ver
`tasks.md`), sem nenhuma chamada HTTP real (fixtures locais de Resenha e listagem in.gov.br,
Princípio VII da constituição) e sem envio real de e-mail (backend `console`/`locmem`).

## 2. Ver um digest de exemplo sem enviar e-mail de verdade

```powershell
python manage.py shell -c "
from datetime import date, datetime
from apps.dou.parsers import parse_resenha_html
from apps.dou.render import render_digest_text
from apps.dou.tests.fixtures import load_fixture
dou_data = parse_resenha_html(load_fixture('resenha_com_publicacoes.json')['html'])
print(render_digest_text(dou_data, terms=['Empresa XYZ'], reference_date=date.today(), now=datetime.now()))
"
```

Conferir manualmente: título do caso e nomes de partes aparecem no texto de forma legível; o
despacho longo do fixture aparece truncado (início + "(...)" + conclusão).

## 3. Validar manualmente contra as fontes reais (opcional, econômico — só 1-2 chamadas)

*Já validado em 2026-09-28 para Resenha e listagem in.gov.br — ver "Correção
pós-implementação" em `research.md` para o que mudou em relação ao design original.
`fetch_sei_publications` (usado pela antecipação, User Story 2) também já foi validado
ao vivo, com um achado negativo ainda sem solução: o formulário de busca de publicações
do SEI parece depender de uma busca assíncrona (AJAX) em vez de aceitar POST direto como
o de busca de processo (feature 008) — hoje a busca real sempre volta vazia (com
segurança: `parse_sei_publications` nunca inventa um item a partir da casca da página).
Encontrar o endpoint AJAX correto fica como acompanhamento pendente antes de considerar
as Histórias 2/3 prontas para produção — ver research.md para o detalhe completo.*

```powershell
python manage.py shell -c "
from datetime import date
from apps.dou.clients import fetch_resenha
print(fetch_resenha(date.today(), timeout=15, user_agent='cade-monitor/1.0'))
"
```

Cenários para conferir manualmente uma única vez cada (são fontes públicas de governo — não
repetir em loop):

1. **Resenha disponível**: um dia útil recente com publicação conhecida do CADE retorna um dict
   não vazio com o conteúdo esperado.
2. **Resenha ainda não publicada / fallback**: simular fora do horário normal de publicação (ou
   usar uma data futura) deve retornar `None` sem lançar exceção; `fetch_ingov_listing` para o
   mesmo dia deve responder (ainda que vazio) sem lançar exceção.

Qualquer divergência entre o formato real da resposta e o assumido em `research.md`/`parsers.py`
deve ser documentada na seção "Correção pós-implementação" de `research.md`, seguindo o modelo da
feature 008.

## 4. Verificar a cadência de 5 minutos e a janela diária

```powershell
python manage.py test apps.dou.tests.test_services -v 2
```

Os testes de `test_services.py` cobrem, com o relógio mockado: (a) duas chamadas seguidas a
`run_digest_window` dentro de 5 min só fazem 1 busca HTTP (mock); (b) fora da janela diária
configurada, nenhuma busca HTTP ocorre.

## Critério de aceite da feature

- Passo 1 (testes automatizados) passa integralmente, cobrindo as três histórias de usuário e os
  edge cases da spec.
- Passo 2 produz um e-mail legível, com negrito e destaque corretos.
- Passo 3 confirma que o formato real das duas fontes bate com o assumido (ou gera a correção
  documentada).
- Passo 4 confirma a cadência mínima de 5 min e o respeito à janela diária (emenda do Princípio II
  v2.2.0).
