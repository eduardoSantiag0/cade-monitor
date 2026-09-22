---

description: "Task list for 005-postgres-render"
---

# Tasks: PostgreSQL gerenciado como banco principal

**Input**: Design documents from `/specs/005-postgres-render/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Incluídos. São obrigatórios pela constituição (Princípio VII e Development Workflow
§2) e pela spec (FR-012).

**Organization**: Tarefas agrupadas por user story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos diferentes, sem dependência)
- **[Story]**: US1–US4 conforme a spec

---

## Phase 1: Setup

- [X] T001 Adicionar `psycopg[binary]==3.3.6` em `requirements.txt`, com comentário apontando para a constituição v2.0.0 / Princípio VIII
- [X] T002 [P] Adicionar serviço opcional `postgres` (`postgres:18-alpine`, profile `pg`, volume nomeado, user/db `cade`) em `docker-compose.yml`
- [X] T003 [P] Documentar `DATABASE_URL` (linha comentada, só placeholders), `DB_SSLMODE` e `DB_CONN_MAX_AGE` em `.env.example`, conforme `contracts/env-vars.md`

---

## Phase 2: Foundational (bloqueia todas as stories)

- [X] T004 Adicionar `database_url: str | None`, `db_sslmode: str = 'require'` e `db_conn_max_age: int = 60` em `config/env_schema.py`. Em `from_env`, `database_url` só é preenchida se a variável existir. O validator rejeita valor vazio e `db_sslmode` fora da lista permitida (research R3/R5)
- [X] T005 Criar `config/database.py` com `database_config_from_url()` (parse com stdlib, `unquote`, porta padrão, `sslmode` da query com precedência, `ImproperlyConfigured` com senha mascarada) e `build_databases(env)` (research R2/R3)
- [X] T006 Trocar o bloco `DATABASES` de `config/settings.py` por `build_databases(env)`, mantendo `SQLITE_PATH` e atualizando o comentário do cabeçalho
- [X] T007 [P] Testes do helper em `tests/test_database_config.py`: URL completa, `postgres://`, porta padrão, senha com `@`/`%40`, `?sslmode=disable` sobrepondo `DB_SSLMODE`, esquema inválido, host ou nome ausente, mensagem sem senha, variável ausente → SQLite, variável vazia → erro

**Checkpoint**: a aplicação escolhe o banco pela env. A suíte roda nos dois bancos.

---

## Phase 3: User Story 1 — Produção sobre o banco gerenciado (P1) 🎯 MVP

**Goal**: Web, worker e comandos usam o Postgres quando `DATABASE_URL` está definida, com
conexões resilientes.

**Independent Test**: quickstart §2 e §4 (`connection.vendor == 'postgresql'`, `migrate` limpo,
checagem gravada).

- [X] T008 [US1] Chamar `django.db.close_old_connections()` no início de `_run_cycle` e após exceção no loop em `apps/monitoring/management/commands/run_worker.py` (research R4, SC-006)
- [X] T009 [P] [US1] Ordenação com `F('last_checked_at').asc(nulls_first=True)` em `apps/monitoring/scheduler.py::get_due_processes`
- [X] T010 [P] [US1] `MonitoredProcess.Meta.ordering` com `F('last_changed_at').desc(nulls_last=True)` em `apps/processes/models.py` e o mesmo em `apps/processes/selectors.py::get_all_processes`. Gerar a migration `AlterModelOptions` em `apps/processes/migrations/`
- [X] T011 [P] [US1] Truncar `document_number` em `[:120]` em `apps/monitoring/services.py::_persist_detected_documents`
- [X] T012 [P] [US1] Testes em `tests/test_monitoring.py`: processo nunca checado vem primeiro em `get_due_processes`, `document_number` longo é truncado e o worker chama `close_old_connections` a cada ciclo (mock)
- [X] T013 [P] [US1] Teste em `tests/test_processes.py`: processo sem `last_changed_at` aparece depois dos processos com mudança na listagem
- [X] T014 [US1] Adicionar o job `test-postgres` em `.github/workflows/ci.yml` com service `postgres:18` (health check `pg_isready`), `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable`, `makemigrations --check` + suíte completa (FR-008, SC-003)

**Checkpoint**: MVP. Dá para fazer o deploy no Render com Postgres.

---

## Phase 4: User Story 2 — Dev e testes sem o banco gerenciado (P1)

**Goal**: Sem `DATABASE_URL`, nada muda em relação ao comportamento atual.

**Independent Test**: quickstart §1.

- [X] T015 [US2] Atualizar a docstring de `apps/monitoring/apps.py` deixando claro que os PRAGMAs valem só para o SQLite de dev e testes (a lógica já verifica `vendor`)
- [X] T016 [P] [US2] Teste em `tests/test_database_config.py`: `build_databases` sem URL retorna exatamente o bloco SQLite atual (ENGINE, NAME=`SQLITE_PATH`, `timeout=20`)
- [X] T017 [US2] Rodar `python manage.py test tests` sem `DATABASE_URL` e confirmar que nenhum teste existente foi alterado para passar (SC-002)

---

## Phase 5: User Story 3 — Migração de dados (P2)

**Goal**: Procedimento reproduzível de SQLite → Postgres sem perda nem alertas falsos.

**Independent Test**: quickstart §3 com uma cópia do banco real e as contagens idênticas.

- [X] T018 [US3] Mover o procedimento de migração do `quickstart.md` para uma seção "Migrar de SQLite para PostgreSQL" em `README.md`, incluindo o `sqlsequencereset` e o aviso para apagar `data/migration.json`
- [ ] T019 [US3] ⏳ *Pendente: requer Docker/Postgres local.* Executar o ensaio de migração localmente (SQLite com dados → Postgres do docker-compose), validar SC-004 e SC-005 e registrar o resultado em `specs/005-postgres-render/checklists/requirements.md` (Notes)

---

## Phase 6: User Story 4 — Backup por vendor (P3)

**Goal**: `backup_db` correto nos dois bancos, sem quebrar o scheduler.

**Independent Test**: quickstart §6 e a tabela de `contracts/backup-db.md`.

- [X] T020 [US4] Refatorar `apps/monitoring/management/commands/backup_db.py`: `_backup_sqlite()` (atual) e `_backup_postgres()` (`shutil.which('pg_dump')`, subprocess com `PGPASSWORD`/`PGSSLMODE` no env, `-Fc`, remoção de arquivo parcial em caso de falha, aviso + exit 0 sem `pg_dump`). A rotação é feita por extensão. Atualizar `help`
- [X] T021 [P] [US4] Testes em `tests/test_backup_db.py`: sqlite feliz e arquivo ausente, postgres sem `pg_dump` (aviso e exit 0), postgres com `pg_dump` mockado (sucesso, falha que remove o parcial, senha ausente do argv)

---

## Phase 7: Polish & Cross-Cutting

- [X] T022 [P] Atualizar `README.md`: tabela de stack (PostgreSQL 18 / SQLite dev), tabela de variáveis (`DATABASE_URL`, `DB_*`), Internal vs External URL do Render e o comentário do docker-compose
- [X] T023 [P] Atualizar comentários de `docker-compose.yml` (volume `./data` agora é só do SQLite dev e dos backups)
- [X] T024 Marcar os itens ⚠ do Sync Impact Report da constituição que forem resolvidos (README, `.env.example`) em `.specify/memory/constitution.md`
- [X] T025 Varredura por credenciais reais: `git grep` pelo host, usuário e senha reais da instância (digitados só no terminal, nunca escritos em arquivo) deve retornar zero ocorrências (SC-007)
- [ ] T026 ⏳ *Parcial: §1 e §6 (SQLite) validados; §2 e §5 requerem Postgres local ou o CI.* Executar a validação completa do `quickstart.md` (§1, §2, §5 e §6)

---

## Dependencies & Execution Order

- **Setup (T001–T003)** → **Foundational (T004–T007)** → stories.
- **US1** e **US2** dependem só da Phase 2 e podem rodar em paralelo. US2 é basicamente
  verificação.
- **US3** depende de US1 (Postgres funcional) para o ensaio T019.
- **US4** depende só da Phase 2.
- **Polish** vem depois das stories desejadas.

Dentro de cada fase: T005 → T006 (o settings depende do helper). T004 → T005. T010 gera
migration e precisa rodar antes dos testes da suíte completa.

## Parallel Example: User Story 1

```text
T009 scheduler.py   | T010 processes/models.py + selectors.py | T011 monitoring/services.py
T012 test_monitoring.py | T013 test_processes.py
```

## Implementation Strategy

1. **MVP**: Phases 1–3 (US1). Já dá para fazer o deploy no Render com o Postgres e liberar a
   feature 006 (bot do Telegram).
2. Em seguida, US2 (garantia de não regressão, barata), US4 (backup) e US3 (migração de dados na
   virada de produção).
3. Polish e validação final do quickstart.
