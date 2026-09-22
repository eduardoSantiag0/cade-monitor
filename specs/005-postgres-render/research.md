# Research: PostgreSQL gerenciado como banco principal

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-09-22

## R1 — Driver PostgreSQL

- **Decision**: `psycopg[binary]==3.3.6`, que instala `psycopg` + `psycopg-binary` fixados em
  versão exata, seguindo a política de pins do `requirements.txt`.
- **Rationale**: O Django 5.2 suporta oficialmente o psycopg 3 (é o driver recomendado) e o
  PostgreSQL 14+, o que inclui o 18. O extra `binary` traz a libpq embutida em wheels, então a
  imagem `python:3.12-slim` não precisa de `libpq-dev` nem de compilador, e a imagem continua
  enxuta (Princípio I).
- **Alternatives considered**: `psycopg2-binary` (legado; o próprio projeto desaconselha o uso
  do binário em produção); `psycopg` puro + libpq do sistema (exige `apt-get install libpq5` e
  deixa a imagem maior); `psycopg[c]` (exige compilação no build).

## R2 — Parse da `DATABASE_URL`

- **Decision**: Helper próprio `config/database.py::database_config_from_url(url, *, conn_max_age,
  sslmode)` usando `urllib.parse.urlsplit` + `parse_qs`. Ele retorna o dict no formato de
  `DATABASES['default']`, e um `ValueError` com mensagem clara vira erro de configuração na
  subida.
- **Rationale**: Princípio VIII (evitar dependência nova quando a stdlib resolve). O formato da
  URL do Render é o padrão `postgresql://user:pass@host[:port]/db[?params]`. O helper precisa
  tratar: esquemas `postgres`/`postgresql`, porta padrão 5432, `unquote` de usuário e senha
  (senhas com `@`, `/`, `%`) e o parâmetro `sslmode` da query, que tem precedência sobre o
  default.
- **Alternatives considered**: `dj-database-url` (mais uma dependência para cerca de 30 linhas de
  código); variáveis separadas `DB_HOST`/`DB_USER`/... (o Render entrega uma URL pronta, e
  separar em várias variáveis aumenta o risco de configuração errada).

## R3 — Seleção do banco e fallback

- **Decision**:
  - `DATABASE_URL` **ausente** → SQLite (bloco atual, sem mudanças).
  - `DATABASE_URL` **presente e válida** → PostgreSQL.
  - `DATABASE_URL` **presente mas vazia ou inválida** → erro na subida (FR-007).
- **Rationale**: Uma variável definida com valor vazio (ex.: `DATABASE_URL=` herdado do
  `.env.example`) quase sempre é erro de deploy. Cair em silêncio no SQLite faria a produção
  gravar num arquivo efêmero do container, que é o pior cenário possível. Por isso o
  `.env.example` deixa a linha **comentada**.
- **Alternatives considered**: tratar string vazia como ausente (é mais tolerante, mas esconde
  erro de deploy).

## R4 — Conexões persistentes e resiliência

- **Decision**: `CONN_MAX_AGE=60` (configurável via `DB_CONN_MAX_AGE`) e
  `CONN_HEALTH_CHECKS=True`.
- **Rationale**: Evita o handshake TLS a cada request (que é caro até o Render) e a health check
  descarta conexões encerradas pelo provedor antes do uso (Edge Case "conexões ociosas"). No
  worker, `run_check` roda fora do ciclo request/response, então é preciso chamar
  `django.db.close_old_connections()` no início de cada ciclo do `run_worker`. Isso aplica as
  mesmas regras de idade e saúde e atende o SC-006 (recuperação em até 1 ciclo). Hoje o worker
  nunca fecha conexões, o que no SQLite não importava.
- **Conexões totais**: web = 1 worker × 2 threads = até 2, worker = 1, scheduler = 1 por
  execução. São no máximo cerca de 4 conexões, bem abaixo do limite de qualquer plano do Render.
- **Alternatives considered**: pgbouncer / pooling do psycopg (Over-engineering para essa
  escala); `CONN_MAX_AGE=0` (reconecta a cada request, o que deixa tudo mais lento com TLS).

## R5 — TLS

- **Decision**: `OPTIONS={'sslmode': <valor>}`, com default `require` (`DB_SSLMODE`). Se a URL
  trouxer `?sslmode=`, esse valor tem precedência.
- **Rationale**: FR-005. A URL **externa** do Render exige TLS. Pela URL **interna**, o Render
  aceita TLS também, então `require` funciona nos dois casos e o default é seguro. Quem precisar
  (ex.: Postgres local no docker-compose sem TLS) configura `DB_SSLMODE=disable` ou
  `?sslmode=disable`.
- **Alternatives considered**: `verify-full` (exige distribuir o certificado da CA do Render;
  fica como melhoria futura, documentada no quickstart).

## R6 — Backup no PostgreSQL

- **Decision**: `backup_db` passa a verificar o vendor. No SQLite, mantém o comportamento atual.
  No PostgreSQL, se `pg_dump` estiver no PATH, gera `cade-monitor_<ts>.dump` (formato custom
  `-Fc`) com rotação `--keep`, passando a senha via env `PGPASSWORD` do subprocess (nunca na
  linha de comando). Se `pg_dump` não existir, escreve um aviso explicando que o backup é
  gerenciado pelo Render e termina com código 0.
- **Rationale**: FR-010 / User Story 4. Não vamos instalar `postgresql-client` na imagem: o
  pacote do Debian bookworm é a versão 15, e o `pg_dump` precisa ser de versão ≥ à do servidor
  (18). Um dump seria recusado de qualquer forma, e instalar a partir do repositório PGDG
  aumentaria a imagem sem necessidade. Assim, o scheduler diário não falha.
- **Alternatives considered**: `dumpdata` em JSON (lento e sem garantia de consistência; fica
  só para a migração única, ver R7); remover o comando (quebraria o docker-compose e o Makefile).

## R7 — Migração de dados SQLite → PostgreSQL

- **Decision**: Procedimento documentado no `quickstart.md`, sem comando novo:
  1. Parar o worker.
  2. `dumpdata --natural-foreign --exclude contenttypes --exclude auth.permission
     --exclude admin.logentry --exclude sessions -o data/migration.json` apontando para o SQLite.
  3. `migrate` no Postgres (com `DATABASE_URL` definida).
  4. `loaddata data/migration.json`.
  5. Rodar `sqlsequencereset` para todos os apps e executar o SQL gerado, para que os próximos
     IDs não colidam com os que foram importados.
  6. Validar as contagens comparando os dois bancos (script de uma linha no quickstart).
  7. Subir o worker.
- **Rationale**: FR-009 / SC-004 / SC-005. O `dumpdata` preserva PKs e relacionamentos. Como
  `last_hash` e `last_text` vêm junto, a linha de base é preservada e não há alerta de "primeira
  leitura" (SC-005). O arquivo fica em `data/`, que já está no `.gitignore`.
- **Alternatives considered**: `pgloader` (ferramenta externa, pouco familiar); um management
  command de cópia (código de uso único, que não compensa manter).

## R8 — Portabilidade das migrations e das queries

- **Decision**: Não há mudanças previstas. A varredura não encontrou `RawSQL`, `.extra()`,
  `cursor()` (exceto os PRAGMAs, que já estão protegidos por `vendor == 'sqlite'`), `__regex` nem
  `JSONField`. O CI ganha um job com `postgres:18` para validar `migrate` e rodar a suíte
  inteira (FR-008 / FR-012 / SC-003).
- **Pontos de atenção** que os testes no Postgres devem cobrir:
  - Ordenação com `NULL`s (`order_by('last_checked_at')` em `scheduler.get_due_processes`). O
    Postgres coloca `NULL` **por último** em ASC e o SQLite coloca **primeiro**. Isso inverte a
    prioridade de "nunca checados", então é preciso usar
    `F('last_checked_at').asc(nulls_first=True)`.
  - O caso inverso: `MonitoredProcess.Meta.ordering = ['-last_changed_at', ...]` e
    `processes.selectors` (DESC). O Postgres coloca `NULL` **primeiro** em DESC, então processos
    sem mudança subiriam para o topo das listagens. É preciso usar
    `F('last_changed_at').desc(nulls_last=True)` no `Meta.ordering` e no selector.
  - `max_length` de `CharField` é validado de verdade no Postgres (no SQLite não é): textos do
    SEI em `CharField` precisam ser truncados antes de salvar. `DetectedDocument.title` já é
    truncado (`[:240]`), mas `document_number` (max 120) **não é**. Truncar em
    `apps/monitoring/services.py::_persist_detected_documents`.
  - Comparações de string que dependiam do case-insensitive do SQLite (`LIKE`) ou de
    `icontains`: continuam iguais no ORM.
- **Alternatives considered**: nenhuma.

## R9 — Testes locais contra o Postgres

- **Decision**: Com `DATABASE_URL` definida, `python manage.py test` cria `test_<db>` no próprio
  servidor. **Isso não funciona no Render** (o usuário não tem permissão de `CREATE DATABASE` e
  não é recomendável rodar testes contra o banco de produção). Para dev, adicionamos um serviço
  opcional `postgres` (imagem `postgres:18-alpine`, sob o profile `pg`) no `docker-compose.yml`.
  O CI usa um service container.
- **Rationale**: SC-003 sem arriscar a produção.
