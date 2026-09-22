# Quickstart: Validação da Hardening e Limpeza Técnica do Repositório

Guia de validação ponta a ponta para cada requisito funcional de `spec.md`. Não contém código de
implementação — apenas comandos para provar que cada FR foi atendido. Pré-requisito: repositório
clonado, `.venv` com `requirements.txt` instalado, `.env` configurado a partir de `.env.example`.

## FR-001 — Dados binários do Postgres fora do índice do git

```bash
git ls-files | grep -c "^data/evolution-postgres/"   # esperado: 0
git ls-files | grep -c "^data/evolution-redis/"       # esperado: 0
git status --short | grep "data/evolution-postgres"   # esperado: nenhuma saída (nem "??", nem "M")
```

## FR-002 — README restaurado e coerente com o projeto atual

```bash
test -f README.md && echo "README existe"
```

Revisão manual: abrir `README.md` e confirmar que os comandos de "início rápido" batem com
`.env.example` e com `docker-compose.yml` atuais.

## FR-003 — Falha explícita com `SECRET_KEY` inseguro em produção

```bash
DEBUG=false SECRET_KEY="" python manage.py check
# esperado: processo encerra com erro claro mencionando SECRET_KEY, não um traceback genérico

DEBUG=false SECRET_KEY="django-insecure-troque-antes-de-colocar-em-producao" python manage.py check
# esperado: mesmo erro (valor padrão também é rejeitado)

DEBUG=false SECRET_KEY="uma-chave-realmente-aleatoria-e-longa-o-suficiente" python manage.py check
# esperado: passa normalmente
```

## FR-004 — Código legado removido sem referências soltas

```bash
test -d cademon && echo "FALHOU: cademon/ ainda existe" || echo "OK: cademon/ removido"
test -d wa-bot && echo "FALHOU: wa-bot/ ainda existe" || echo "OK: wa-bot/ removido"
grep -rn "cademon\|wa-bot" --include="*.py" --include="*.md" --include="*.sh" . \
  --exclude-dir=.git --exclude-dir=specs
# esperado: nenhuma ocorrência fora de specs/ (onde o histórico desta decisão fica documentado)
```

## FR-005 — Makefile sem duplicação

```bash
grep -c "^install:" Makefile   # esperado: 1 (hoje: 2)
grep -c "^test:" Makefile      # esperado: 1 (hoje: 2)
```

## FR-006 — Dependências fixadas em versão exata

```bash
grep -E ">=|<=|~=" requirements.txt
# esperado: nenhuma saída — todas as linhas usam "=="
```

## FR-007 — CI rodando a suíte automaticamente

Abrir um Pull Request de teste com uma alteração que quebra deliberadamente um teste existente
(ex.: um `assert False` temporário em `tests/test_processes.py`) e confirmar que o check do
GitHub Actions aparece como falho no PR, sem nenhum comando manual.

## FR-008 — Views de envio manual sem duplicação

```bash
wc -l apps/processes/views.py
# esperado: redução de pelo menos 60% nas linhas hoje ocupadas pelas 4 views de envio manual
# (medir antes/depois; ver SC-006 em spec.md)
```

Revisão manual: confirmar que `process_send_test_email`, `process_notify_subscribers`,
`process_send_test_whatsapp` e `process_send_latest_update` chamam uma função comum para iterar
assinaturas e contar envios/falhas por canal.

## FR-009 — WhatsApp não baixa mais o anexo inteiro

Teste automatizado (a ser adicionado): mockar `download_document` em
`apps/notifications/services.py` e confirmar que, para uma notificação `NotificationChannel.WHATSAPP`
com um documento em modo `attachment`, `download_document` **não é chamado**; para
`NotificationChannel.EMAIL`, continua sendo chamado normalmente.

## FR-010 — Falhas do worker chegam a um serviço externo

Com `SENTRY_DSN` configurado num ambiente de teste, forçar uma exceção não tratada dentro do loop
de `run_worker` (ex.: processo com URL malformada de propósito) e confirmar que o evento aparece
no painel do serviço de rastreamento configurado, além do log local.

## FR-011 — Aplicação funcional com Redis desabilitado

```bash
python manage.py test tests.test_monitoring -v 2
# esperado: o teste novo que roda run_check com PROCESS_HASH_REDIS_ENABLED=False passa,
# confirmando detecção correta de mudança/sem-mudança via MonitoredProcess.last_hash
```

## Validação de regressão geral

```bash
make test
# esperado: suíte inteira passa, sem depender de cademon/ (removido no FR-004)
```
