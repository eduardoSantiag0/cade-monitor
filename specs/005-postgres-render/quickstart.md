# Quickstart: PostgreSQL gerenciado como banco principal

**Feature**: [spec.md](./spec.md) | Contratos: [env-vars](./contracts/env-vars.md),
[backup-db](./contracts/backup-db.md)

## Pré-requisitos

- `pip install -r requirements.txt` (inclui `psycopg[binary]`).
- Para o cenário 2: Docker (Postgres local) **ou** acesso à External URL do Render.
- ⚠️ Use sempre a senha **rotacionada** do Render, guardada só no `.env` / env vars do Render.

## 1. Fallback SQLite (User Story 2)

```bash
# sem DATABASE_URL no ambiente
python manage.py test tests
python manage.py shell -c "from django.db import connection; print(connection.vendor)"
```

**Esperado**: todos os testes passam e a saída é `sqlite`.

## 2. PostgreSQL local (User Stories 1 e 2, FR-012)

```bash
docker compose --profile pg up -d postgres
export DATABASE_URL="postgresql://cade:cade@localhost:5432/cade?sslmode=disable"
python manage.py migrate
python manage.py test tests
python manage.py shell -c "from django.db import connection; print(connection.vendor)"
```

**Esperado**: o `migrate` roda sem erros, todos os testes passam e a saída é `postgresql`.

## 3. Migrar dados do SQLite

Com o worker **parado**:

```bash
# 3.1 exportar do SQLite (sem DATABASE_URL)
unset DATABASE_URL
python manage.py dumpdata --natural-foreign \
  --exclude contenttypes --exclude auth.permission \
  --exclude admin.logentry --exclude sessions \
  -o data/migration.json

# 3.2 importar no Postgres (External URL do Render, com TLS)
export DATABASE_URL="postgresql://<user>:<senha>@<host>.<regiao>-postgres.render.com/<db>"
python manage.py migrate
python manage.py loaddata data/migration.json

# 3.3 reajustar sequences
python manage.py sqlsequencereset processes subscribers monitoring notifications auth \
  | python manage.py dbshell
```

**Validação (SC-004)**: rode este comando uma vez com `DATABASE_URL` definida e outra sem.
As duas saídas devem ser idênticas.

```bash
python manage.py shell -c "from django.apps import apps; \
[print(m._meta.label, m.objects.count()) for m in apps.get_models() \
 if m._meta.app_label in ('processes','subscribers','monitoring','notifications')]"
```

**Validação (SC-005)**: suba o worker e rode `python manage.py run_worker --once`. Nenhum
processo migrado deve gerar "Primeira leitura registrada" nem uma mudança nova.

Por fim, apague `data/migration.json`, porque ele contém dados de assinantes.

## 4. Produção no Render (User Story 1)

1. Nas env vars dos serviços web e worker, defina `DATABASE_URL` = *Internal Database URL*.
2. Faça o deploy, rode `python manage.py migrate` (release command / shell do Render) e
   `createsuperuser`, se o banco for novo.
3. Cadastre um processo pelo painel e acione "checar agora".

**Esperado**: o processo aparece no painel, e o `CheckRun` e o `PageSnapshot` ficam gravados no
Postgres.

## 5. Resiliência (SC-006, edge cases)

- Com o Postgres local: `docker compose stop postgres` enquanto o worker roda, espere 1 ciclo e
  depois `docker compose start postgres`.
  **Esperado**: o worker loga o erro do ciclo e volta a checar no próximo, sem reinício manual.
- `DATABASE_URL=` (vazia) e depois `python manage.py check`.
  **Esperado**: erro de configuração claro, sem fallback para o SQLite.
- `DATABASE_URL=postgresql://u:SENHA@host/db` com host inválido.
  **Esperado**: erro de conexão que não contém `SENHA`.

## 6. Backup (User Story 4)

```bash
python manage.py backup_db --dest backups   # com e sem DATABASE_URL
```

**Esperado**: o resultado segue a tabela em [contracts/backup-db.md](./contracts/backup-db.md).
Sem `pg_dump` no PATH, o comando mostra o aviso e retorna exit 0.
