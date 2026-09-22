# Implementation Plan: PostgreSQL gerenciado como banco principal

**Branch**: `005-postgres-render` | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-postgres-render/spec.md`

## Summary

Tornar o PostgreSQL 18 gerenciado (Render) o banco principal, selecionado por `DATABASE_URL`,
mantendo o SQLite atual como fallback de dev e testes. Abordagem: um helper em stdlib
(`config/database.py`) converte a URL em `DATABASES['default']`, com TLS, conexões persistentes
e health checks. O worker passa a reciclar conexões a cada ciclo. Também corrigimos três
diferenças de comportamento entre SQLite e Postgres que a pesquisa encontrou (ordenação de
`NULL` em dois lugares e um `CharField` sem truncar), o `backup_db` passa a verificar o vendor, e
o CI ganha um job contra `postgres:18`. O modelo de dados não muda.

## Technical Context

**Language/Version**: Python 3.11 (dev, `.venv`) / 3.12 (imagem `python:3.12-slim` e CI).

**Primary Dependencies**: Django 5.2.15, pydantic 2.13 (`config/env_schema.py`). **Nova:**
`psycopg[binary]==3.3.6` (justificativa: constituição v2.0.0, Princípio VIII; research R1).

**Storage**: PostgreSQL 18 gerenciado (Render) em produção; SQLite (WAL) em dev e testes.

**Testing**: `python manage.py test tests` (Django `TestCase`/`SimpleTestCase`). O CI roda a
suíte duas vezes, em SQLite e em Postgres 18 (service container).

**Target Platform**: Linux containers (Docker / Render). Web: Gunicorn 1 worker × 2 threads.
Worker: `run_worker`.

**Project Type**: Web service Django monolítico.

**Performance Goals**: Nenhuma regressão perceptível no painel. A latência até o banco gerenciado
é compensada pelas conexões persistentes (`CONN_MAX_AGE=60`).

**Constraints**: No máximo ~4 conexões simultâneas (research R4). Nenhuma credencial no
repositório. `DATABASE_URL` inválida impede a subida.

**Scale/Scope**: Dezenas a poucas centenas de processos monitorados. A escala não muda nesta
feature.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.* Referência:
constituição **v2.0.0**.

| Princípio | Verificação | Status |
|---|---|---|
| I. Simplicidade Operacional | Nenhum processo novo. Sem pooler externo. `psycopg[binary]` evita dependências de sistema na imagem. Redis intocado. | ✅ |
| II. Monitoramento Responsável | Cadência e scraping inalterados. A correção de `nulls_first` só restaura a prioridade atual dos processos nunca checados. | ✅ |
| III. Django Monolítico | Helper em `config/`. A lógica continua em services e selectors. Nenhum app novo. | ✅ |
| IV. PostgreSQL em Produção | `DATABASE_URL` só no ambiente, `sslmode=require` por padrão, migrations portáveis validadas no CI, PRAGMAs só com `vendor == 'sqlite'`, worker único. | ✅ |
| V. Notificações | Não afetado. | ✅ N/A |
| VI. Humanização | Não afetado. | ✅ N/A |
| VII. Qualidade | Testes do helper de URL, do fallback, do backup por vendor e das ordenações. Suíte rodando em dois bancos no CI. Mensagens de erro claras sem vazar a senha. | ✅ |
| VIII. Sem Over-Engineering | Uma dependência, já justificada na constituição. Sem `dj-database-url`, sem pgbouncer. | ✅ |

**Post-design re-check (Phase 1)**: ✅ sem violações. O design não adicionou processos,
dependências ou serviços além dos previstos.

## Project Structure

### Documentation (this feature)

```text
specs/005-postgres-render/
├── plan.md              # Este arquivo
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── env-vars.md      # Contrato de configuração (DATABASE_URL, DB_*)
│   └── backup-db.md     # Contrato do comando backup_db por vendor
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit.tasks)
```

### Source Code (repository root)

```text
config/
├── database.py          # NOVO — database_config_from_url() + build_databases()
├── env_schema.py        # + database_url (Optional), db_conn_max_age, db_sslmode
└── settings.py          # DATABASES = build_databases(env)

apps/monitoring/
├── apps.py              # docstring: PRAGMAs só no SQLite (sem mudança de lógica)
├── scheduler.py         # order_by nulls_first=True
├── services.py          # truncar document_number[:120]
└── management/commands/
    ├── backup_db.py     # verifica o vendor: sqlite (atual) | postgres (pg_dump ou aviso)
    └── run_worker.py    # close_old_connections() a cada ciclo

apps/processes/
├── models.py            # Meta.ordering com nulls_last (+ migration só de Meta)
└── selectors.py         # order_by nulls_last

tests/
├── test_database_config.py   # NOVO — helper de URL e seleção de banco
├── test_backup_db.py         # NOVO — backup por vendor (pg_dump mockado)
└── test_monitoring.py        # + ordenação de processos nunca checados

requirements.txt          # + psycopg[binary]==3.3.6
.env.example              # + DATABASE_URL (comentada), DB_CONN_MAX_AGE, DB_SSLMODE
docker-compose.yml        # + serviço opcional postgres:18-alpine (profile "pg")
.github/workflows/ci.yml  # + job test-postgres com service postgres:18
README.md                 # stack e configuração de banco
```

**Structure Decision**: Mantém a estrutura Django monolítica existente. O único módulo novo é
`config/database.py`, porque a construção de `DATABASES` é configuração de projeto (não é
domínio) e precisa ser testável fora do `settings.py`.

## Design Notes

1. **`config/database.py`**
   - `database_config_from_url(url: str, *, conn_max_age: int, sslmode: str) -> dict`: aceita
     `postgres://` e `postgresql://`, faz `unquote` de usuário e senha, usa a porta 5432 por
     padrão e dá precedência ao `sslmode` da query. Lança `ImproperlyConfigured` com mensagem
     que **nunca inclui a senha** (mascarar com `***`).
   - `build_databases(env) -> dict`: se `env.database_url is None`, retorna o bloco
     SQLite atual (copiado de `settings.py` sem mudanças). Se não, retorna o bloco Postgres.
2. **`env_schema.py`**: `database_url: str | None = None`. Em `from_env`, a variável só é
   preenchida se estiver presente no ambiente. Se estiver presente e vazia (depois de `strip()`),
   um validator lança erro (research R3).
3. **Worker**: chamar `close_old_connections()` no início de `_run_cycle` e dentro do `except`
   do loop, antes do próximo ciclo (research R4, SC-006).
4. **Ordenação**: `scheduler.get_due_processes` usa `F('last_checked_at').asc(nulls_first=True)`.
   `MonitoredProcess.Meta.ordering` e `selectors.get_all_processes` usam
   `F('last_changed_at').desc(nulls_last=True)` (research R8). Isso gera uma migration só de
   `Meta` (sem alteração de schema).
5. **Backup**: conforme [contracts/backup-db.md](./contracts/backup-db.md).

## Complexity Tracking

Sem violações da constituição. Seção não aplicável.
