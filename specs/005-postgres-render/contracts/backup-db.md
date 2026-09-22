# Contract: `python manage.py backup_db`

Argumentos inalterados: `--dest DIR` (padrão `<BASE_DIR>/backups`) e `--keep N` (padrão 7;
`0` = manter todos).

## Comportamento por vendor

| Vendor | Condição | Ação | Saída | Exit code |
|---|---|---|---|---|
| sqlite | arquivo existe | `sqlite3.Connection.backup()` → `cade-monitor_<ts>.sqlite3`, rotação | `Backup criado: <path> (<n> KB)` | 0 |
| sqlite | arquivo não existe | — | `Banco não encontrado: <path>` | ≠0 (`CommandError`) |
| postgresql | `pg_dump` no PATH | `pg_dump -Fc -h -p -U -d` com `PGPASSWORD`/`PGSSLMODE` no env do subprocess → `cade-monitor_<ts>.dump`, rotação | `Backup criado: <path> (<n> KB)` | 0 |
| postgresql | `pg_dump` falha (ex.: versão menor que a do servidor) | apaga o arquivo parcial | `Falha no pg_dump: <stderr sem senha>` | ≠0 (`CommandError`) |
| postgresql | `pg_dump` ausente | — | `AVISO: pg_dump não encontrado; o backup do PostgreSQL é gerenciado pelo provedor (Render). Nada a fazer.` | 0 |

A rotação `--keep` considera apenas arquivos com a extensão do vendor atual (`.sqlite3` ou
`.dump`).

A senha **nunca** é passada como argumento de linha de comando (ela ficaria visível no `ps`).
