# CADE Monitor

Radar leve de acompanhamento de processos públicos do CADE/SEI.
Avisa assinantes por e-mail ou WhatsApp quando houver nova movimentação ou qualquer alteração
relevante no texto extraído de uma página pública.

> O sistema apenas consulta páginas públicas, extrai conteúdo visível, compara com versões
> anteriores e registra mudanças. Não acessa dados privados, não burla autenticação e não
> modifica nenhuma informação.

Este projeto segue o workflow de [Spec Kit](https://github.com/github/spec-kit) (Spec-Driven
Development) — specs, planos e tarefas de cada feature ficam em `specs/`, e os princípios
arquiteturais do projeto ficam documentados em `.specify/memory/constitution.md`.

---

## Stack

| Camada    | Tecnologia                     |
| --------- | ------------------------------ |
| Backend   | Django 5.x                     |
| Banco     | PostgreSQL 18 (Render) — produção |
| Banco dev | SQLite (WAL mode) — dev/testes |
| Interface | Django templates + CSS próprio |
| Admin     | Django Admin                   |
| Worker    | `management command` em loop   |
| WSGI      | Gunicorn                       |
| Telegram  | Bot API (webhook) — canal principal |
| WhatsApp  | Evolution API (opcional)       |
| E-mail    | SMTP via `django.core.mail`    |
| Container | Docker + Docker Compose        |

---

## Início rápido (desenvolvimento)

```bash
# 1. Crie e ative o virtualenv
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\Activate.ps1 # Windows

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Configure o ambiente
cp .env.example .env
# Edite .env com valores reais (nunca comite o .env)

# 4. Aplique as migrations e crie o superusuário
python manage.py migrate
python manage.py createsuperuser

# 5. Rode o servidor de desenvolvimento
python manage.py runserver

# 6. Em outro terminal, rode o worker de monitoramento
python manage.py run_worker
```

Acesse `http://localhost:8000` para o painel e `http://localhost:8000/admin` para o Django Admin.

---

## Deploy com Docker

```bash
cp .env.example .env
# Edite .env: SECRET_KEY segura, ALLOWED_HOSTS, SMTP, Evolution API

docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Os serviços `web`, `worker` e `scheduler` compartilham a mesma imagem (`Dockerfile`); veja
`docker-compose.yml` para o papel de cada um e para o serviço opcional `evolution-api`.

---

## Management commands

```bash
# Worker contínuo (usado no Docker Compose)
python manage.py run_worker

# Checagem única de todos os processos vencidos (para cron)
python manage.py check_processes

# Checa um processo específico pelo ID
python manage.py check_process --id 1

# Testa extração de texto de uma URL ou número de processo
python manage.py probe_process "https://sei.cade.gov.br/..."
python manage.py probe_process "08700.005905/2026-38"

# Resolve número de processo para URL pública
python manage.py resolve_process "08700.005905/2026-38"

# Envia notificações pendentes (também roda automaticamente no worker)
python manage.py send_pending_notifications

# Resumo diário para todos os assinantes (rodar via cron às 8h)
python manage.py generate_daily_digest
python manage.py generate_daily_digest --hours 48 --dry-run

# Limpeza de snapshots antigos
python manage.py cleanup_snapshots
python manage.py cleanup_snapshots --keep 50 --dry-run

# Backup (SQLite: cópia do arquivo; PostgreSQL: pg_dump se disponível,
# senão avisa que o backup é gerenciado pelo Render)
python manage.py backup_db --dest backups --keep 7
```

---

## Estrutura

```
config/          ← settings, urls, wsgi
apps/
  processes/     ← MonitoredProcess, ProcessTag
  monitoring/    ← CheckRun, PageSnapshot, DetectedChange, scraping, diff
  subscribers/   ← Subscriber, ProcessSubscription
  notifications/ ← Notification, canais email/evolution/telegram
  telegram_bot/  ← bot do Telegram: webhook, comandos, ações do worker
  dashboard/     ← views do painel
templates/       ← HTML templates Django
static/css/      ← CSS próprio
tests/           ← testes automatizados
specs/           ← specs, planos e tarefas (Spec Kit)
```

---

## Páginas públicas suportadas

O sistema aceita dois formatos de fonte ao cadastrar um processo:

1. **URL pública direta** — idealmente o link final de exibição do processo
   (`md_pesq_processo_exibir.php?...`), que é o formato mais estável para monitorar.
2. **Número de protocolo CADE/SEI** — ex: `08700.005905/2026-38`. Nesse caso o sistema envia uma
   consulta pública à página de pesquisa do SEI e segue automaticamente o primeiro link de
   resultado para resolver a URL de detalhe.

A página de pesquisa pública do CADE/SEI fica em:

```
https://sei.cade.gov.br/sei/modulos/pesquisa/md_pesq_processo_pesquisar.php?acao_externa=protocolo_pesquisar&acao_origem_externa=protocolo_pesquisar&id_orgao_acesso_externo=0
```

A página de detalhe de um processo público normalmente contém uma "Lista de Protocolos" e uma
"Lista de Andamentos" — é o texto dessas seções que o monitor compara entre leituras.

---

## Cadastrar um processo

No painel:

1. Informe um rótulo interno para identificar o processo.
2. Cole o link final público do processo ou informe o número de protocolo.
3. Cadastre assinantes (e-mail e, se o WhatsApp estiver configurado, telefone em formato
   internacional) e vincule-os ao processo.
4. Clique em "Checar agora" para gravar a primeira leitura (linha de base) — a partir da próxima
   mudança detectada, os alertas são enviados aos assinantes vinculados.

---

## Variáveis de ambiente

Veja `.env.example` para a lista completa com comentários. Variáveis obrigatórias em produção:

| Variável        | Descrição                                                                              |
| --------------- | -----------------------------------------------------------------------------------------|
| `SECRET_KEY`    | Chave Django — gere com `python -c "import secrets; print(secrets.token_urlsafe(50))"`. Obrigatória e validada: a aplicação recusa iniciar com `DEBUG=false` sem uma chave própria. |
| `ALLOWED_HOSTS` | Domínios permitidos, separados por vírgula                                             |
| `DATABASE_URL`  | URL do PostgreSQL (`postgresql://user:senha@host:5432/db`). Se ausente, usa SQLite. Definida mas vazia = erro. Veja [Banco de dados](#banco-de-dados-postgresql). |
| `SQLITE_PATH`   | Caminho do banco SQLite — usado só sem `DATABASE_URL` (dev/testes)                     |
| `DEBUG`         | `false` em produção                                                                    |

### Banco de dados (PostgreSQL)

Produção usa **PostgreSQL 18 gerenciado no Render**, configurado apenas por `DATABASE_URL`
(nunca versione a URL real — ela contém a senha).

- **Serviços dentro do Render** (web, worker): use a *Internal Database URL*.
- **Acesso de fora** (sua máquina, migração de dados): use a *External Database URL*
  (`*.render.com`), sempre com TLS.
- `DB_SSLMODE` (padrão `require`) e `DB_CONN_MAX_AGE` (padrão `60`) ajustam TLS e conexões
  persistentes; `?sslmode=` na URL tem precedência.
- Sem `DATABASE_URL` a aplicação usa o SQLite local — é o modo de dev e da suíte de testes.
- Postgres local para testes: `docker compose --profile pg up -d postgres` e
  `DATABASE_URL=postgresql://cade:cade@localhost:5432/cade?sslmode=disable`.
  (Não rode a suíte contra o banco do Render.)

#### Migrar de SQLite para PostgreSQL

Com o worker **parado**:

```bash
# 1. exportar do SQLite (sem DATABASE_URL no ambiente)
python manage.py dumpdata --natural-foreign   --exclude contenttypes --exclude auth.permission   --exclude admin.logentry --exclude sessions   -o data/migration.json

# 2. importar no Postgres (External URL, com DATABASE_URL definida)
python manage.py migrate
python manage.py loaddata data/migration.json

# 3. reajustar as sequences para os próximos IDs não colidirem
python manage.py sqlsequencereset processes subscribers monitoring notifications auth   | python manage.py dbshell
```

Compare as contagens por model nos dois bancos (veja
`specs/005-postgres-render/quickstart.md`) e **apague `data/migration.json`** — ele contém
dados de assinantes. Como `last_hash` é migrado, o próximo ciclo do worker não gera alertas de
"primeira leitura".

### E-mail (SMTP)

```
SMTP_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=usuario@example.com
SMTP_PASSWORD=senha-ou-app-password
MAIL_FROM=usuario@example.com
SMTP_TLS=true
```

Sem SMTP habilitado, o backend de console do Django é usado em desenvolvimento — o e-mail aparece
no terminal em vez de ser enviado de verdade.

### Bot do Telegram (canal principal)

Qualquer pessoa (ou grupo) pode acompanhar processos sozinha, pelo Telegram, e receber alertas
de movimentação. O WhatsApp e o e-mail continuam disponíveis para assinantes do painel.

**Configurar**

1. Crie o bot no [@BotFather](https://t.me/BotFather) (`/newbot`) e guarde o token.
2. Configure, nos serviços web **e** worker:
   ```
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=<token>
   TELEGRAM_WEBHOOK_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(32))">
   BASE_URL=https://<seu-app>.onrender.com
   ```
3. Depois do deploy: `python manage.py migrate` e `python manage.py telegram_webhook`
   (confira com `--info`; remova com `--delete`).

**Comandos**

| Comando | O que faz |
|---|---|
| `/start`, `/help` | apresentação e ajuda |
| `/watch <processo>` | começa a monitorar (ex.: `/watch 08700.005905/2026-38`, também aceita o link do SEI) |
| `/unwatch <processo>` | para de monitorar |
| `/list` | processos acompanhados |
| `/status <processo>` | última movimentação conhecida |
| `/check <processo>` | verifica agora (respeita `TELEGRAM_CHECK_COOLDOWN_SECONDS`) |
| `/pause`, `/resume <processo>` | pausa/retoma os alertas só para quem pediu |
| `/history <processo>` | últimas movimentações |

**Como funciona**

- O webhook (`/telegram/webhook/`) só aceita chamadas com o secret, processa cada update uma
  vez e **nunca consulta o SEI**. A primeira leitura do `/watch` e o `/check` viram ações
  executadas pelo `run_worker` (uma consulta por processo por ciclo).
- Cada conversa vira um assinante. Os alertas usam o mesmo fluxo de notificações, tentativas e
  anexos dos outros canais.
- **Grupos:** adicione o bot ao grupo. Só administradores usam `/watch`, `/unwatch`, `/pause`
  e `/resume`. Qualquer membro pode usar `/list`, `/status`, `/history` e `/check`.
- Limite de `TELEGRAM_MAX_PROCESSES_PER_CHAT` processos por conversa (padrão 10).
- Processos criados pelo bot são pausados automaticamente quando ninguém mais os acompanha.
  Processos cadastrados pelo painel nunca têm o status alterado pelo bot.

### WhatsApp (Evolution API)

O único provider de WhatsApp deste projeto é a [Evolution API](https://doc.evolution-api.com/)
self-hosted.

```
EVOLUTION_ENABLED=true
EVOLUTION_API_BASE_URL=http://localhost:8080
EVOLUTION_API_KEY=sua_chave
EVOLUTION_INSTANCE_NAME=cade-monitor
```

Se a Evolution API retornar erro de envio ou a instância estiver desconectada, a falha fica
registrada em `Notification`/`NotificationAttempt` e é reprocessada automaticamente nos próximos
ciclos, até o limite de `MAX_NOTIFICATION_ATTEMPTS`.

---

## Testes

```bash
python manage.py test tests
python manage.py test tests --verbosity=2
```

---

## Cuidados de produção

- Nunca versione o arquivo `.env`.
- Gere uma `SECRET_KEY` própria antes de qualquer deploy — a aplicação recusa subir sem isso em
  produção.
- Use HTTPS em produção (reverse proxy como Nginx/Caddy na frente do Gunicorn).
- O painel exige autenticação Django em todas as rotas.
- Respeite intervalos de checagem responsáveis (mínimo de 25 minutos por processo, ver
  `.specify/memory/constitution.md`) — o sistema consulta páginas públicas de terceiros.
- Valide a página oficial antes de tratar qualquer alerta como prova processual.
- Monitore `logs/cade-monitor.log`. Em produção o backup do PostgreSQL é gerenciado pelo Render;
  em dev, `python manage.py backup_db` copia o SQLite.
