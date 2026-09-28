# Quickstart: validar o cartão de próxima sessão

Pré-requisitos: ambiente configurado conforme o README, tabela de cache criada:

```powershell
python manage.py createcachetable
```

## 1. Rodar a suíte de testes automatizados (sem rede)

```powershell
python manage.py test apps.dashboard
```

Resultado esperado: todos os testes passam, sem nenhuma chamada HTTP real (fixtures locais das
duas páginas do CADE).

## 2. Ver o cartão populado manualmente, sem esperar o worker

```powershell
python manage.py shell -c "
from apps.dashboard.hub import refresh_sessoes, refresh_pauta, proxima_sessao, pauta_url
refresh_sessoes(15, 'cade-monitor/1.0')
refresh_pauta(15, 'cade-monitor/1.0')
sessao = proxima_sessao()
print(sessao)
print(pauta_url(sessao) if sessao else None)
"
```

Depois, abrir o dashboard no navegador (`python manage.py runserver`) e confirmar que o cartão
aparece com a mesma data/título/link.

## 3. Validar manualmente contra as fontes reais (opcional, econômico — só 1-2 chamadas)

O passo 2 já faz isso (`refresh_sessoes`/`refresh_pauta` batem nas fontes reais). Cenários para
conferir uma única vez:

1. O calendário de sessões retorna pelo menos uma sessão futura reconhecida.
2. A página anual de pautas, para o ano/número da sessão em exibição, retorna o link do PDF
   quando ele já estiver publicado (ou `''` sem erro quando ainda não estiver).

Qualquer divergência do formato real deve ser documentada na seção "Correção pós-implementação"
de `research.md`, seguindo o modelo das features 008/009.

## 4. Verificar que a view nunca faz HTTP

```powershell
python manage.py test apps.dashboard.tests.test_hub -v 2
```

Os testes de `test_hub.py` mockam `urllib.request.urlopen` e confirmam que `proxima_sessao()`/
`pauta_url()` nunca o chamam (só leem `cache.get`), e que `refresh_sessoes`/`refresh_pauta`
respeitam a cadência mínima entre tentativas.

## Critério de aceite da feature

- Passo 1 passa integralmente.
- Passo 2 popula o cache e o cartão aparece no dashboard com o conteúdo esperado.
- Passo 3 confirma o formato real das duas fontes (ou gera a correção documentada).
- Passo 4 confirma que a view nunca faz HTTP e que a cadência mínima é respeitada.
