# Contract: Variáveis de ambiente do banco

| Variável | Tipo | Padrão | Obrigatória | Descrição |
|---|---|---|---|---|
| `DATABASE_URL` | URL | *(ausente)* | Não | `postgresql://USER:PASS@HOST[:PORT]/DB[?sslmode=...]`. Se estiver ausente, a aplicação usa o SQLite. Se estiver presente mas vazia ou inválida, a subida falha. |
| `DB_SSLMODE` | str | `require` | Não | `disable`, `allow`, `prefer`, `require`, `verify-ca` ou `verify-full`. É ignorada se a URL tiver `?sslmode=`. |
| `DB_CONN_MAX_AGE` | int ≥ 0 | `60` | Não | Segundos que uma conexão persistente é mantida. `0` = uma conexão por request. |
| `SQLITE_PATH` | path | `data/cade-monitor.sqlite3` | Não | Continua existindo e só é usada no fallback SQLite. |

## Render

- **Serviços dentro do Render** (web, worker): usar a *Internal Database URL*.
- **Acesso externo** (máquina do dev, migração de dados): usar a *External Database URL*
  (host `*.<regiao>-postgres.render.com`), sempre com TLS.

## Garantias

- A senha nunca aparece em mensagens de erro nem em logs (é mascarada como `***`).
- O `.env.example` traz a linha **comentada** com placeholders, nunca valores reais.

## Mensagens de erro (subida)

| Condição | Mensagem (resumo) |
|---|---|
| Variável presente e vazia | `DATABASE_URL está definida mas vazia. Remova a variável para usar SQLite ou informe uma URL postgresql://...` |
| Esquema não suportado | `DATABASE_URL com esquema 'mysql' não suportado; use postgresql://` |
| Faltando host ou nome do banco | `DATABASE_URL incompleta (host e nome do banco são obrigatórios): postgresql://user:***@/` |
