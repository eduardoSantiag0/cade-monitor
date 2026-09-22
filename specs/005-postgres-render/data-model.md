# Data Model: PostgreSQL gerenciado como banco principal

**Feature**: [spec.md](./spec.md) | **Date**: 2026-09-22

Esta feature **não altera o schema** do domínio. Ela muda onde os dados ficam guardados e corrige
três pontos em que SQLite e Postgres se comportam de forma diferente.

## Configuração de conexão (não persistida)

| Campo derivado da URL | Origem | Regra |
|---|---|---|
| `ENGINE` | esquema `postgres`/`postgresql` | outro esquema → erro de configuração |
| `HOST` | hostname | obrigatório |
| `PORT` | porta | padrão `5432` |
| `NAME` | path sem a `/` inicial | obrigatório |
| `USER` / `PASSWORD` | userinfo | `unquote` (suporta `@`, `/`, `%`) |
| `OPTIONS.sslmode` | `?sslmode=` na URL, senão `DB_SSLMODE` | padrão `require` |
| `CONN_MAX_AGE` | `DB_CONN_MAX_AGE` | padrão `60` |
| `CONN_HEALTH_CHECKS` | fixo | `True` |

Estados possíveis de `DATABASE_URL`: **ausente** → SQLite; **válida** → Postgres; **vazia ou
inválida** → a aplicação não sobe.

## Ajustes em entidades existentes (sem mudança de schema)

| Entidade | Ajuste | Motivo |
|---|---|---|
| `processes.MonitoredProcess` | `Meta.ordering` → `F('last_changed_at').desc(nulls_last=True), '-updated_at'` | O Postgres coloca `NULL` primeiro em DESC |
| `monitoring.DetectedDocument` | `document_number` truncado em 120 caracteres ao ser criado | O Postgres aplica `max_length` de verdade |
| (consulta) `scheduler.get_due_processes` | `F('last_checked_at').asc(nulls_first=True)` | Garante que processos nunca checados continuem com prioridade |

A migration gerada para `MonitoredProcess` altera só as `options` de `Meta` (`AlterModelOptions`)
e não tem efeito no banco.

## Migração de dados

Todas as entidades existentes (processos, tags, assinantes, assinaturas, checagens, snapshots,
mudanças, documentos, notificações, tentativas, estados de documento, AppSetting, usuários do
admin) são copiadas com as PKs preservadas. As sequences são reajustadas depois da carga. Veja
[quickstart.md](./quickstart.md#3-migrar-dados-do-sqlite).
