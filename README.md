# CADE Monitor

**Acompanhe processos públicos do CADE pelo Telegram.** Mande o número do processo para o bot
e receba um aviso, com o documento anexado, sempre que surgir uma movimentação nova no SEI.


```
/watch 08700.005905/2026-38
```

> O CADE Monitor só consulta páginas **públicas** do SEI do CADE, respeitando um intervalo mínimo
> entre consultas. Não acessa dados sigilosos, não burla autenticação e não altera nada.
> Confira sempre a página oficial antes de tratar um alerta como prova processual.

---

## Como funciona

```
Você                         CADE Monitor                                SEI/CADE
 │  /watch 08700.…/2026-38      │                                            │
 │ ───────────────────────────► │  valida o número e confirma na hora        │
 │                              │  primeira leitura (estado inicial) ──────► │
 │  ✅ monitorando              │ ◄──────────────────────────────────────────│
 │  🧾 última atualização + PDF │                                            │
 │ ◄─────────────────────────── │                                            │
 │                              │  verifica periodicamente (≥ 25 min) ─────► │
 │                              │  compara com a leitura anterior            │
 │  📬 alerta + documento novo  │  mudou? ─► alerta para todos que acompanham │
 │ ◄─────────────────────────── │                                            │
```

- **Uma consulta serve a todos.** Se dez pessoas acompanham o mesmo processo, o SEI é consultado
  uma vez por ciclo, e todas recebem o alerta.
- **Documentos chegam como arquivo.** Os documentos novos são baixados e enviados no chat. Arquivos
  compactados, ou acima do limite, vão como link.
- **Funciona em grupos.** Adicione o bot a um grupo da equipe: os alertas chegam para todos, e
  só administradores escolhem os processos.

---

## Comandos do bot

| Comando | O que faz |
|---|---|
| `/watch <processo>` | Começa a monitorar. Aceita `08700.005905/2026-38`, `08700005905202638` ou o link público do SEI. Confirma na hora e envia a última atualização com o documento. |
| `/last_update <processo>` | Última atualização conhecida: documento mais recente (com o arquivo), última mudança e link do processo. |
| `/list` | Processos que você acompanha. |
| `/status <processo>` | Situação, última verificação e últimas movimentações. |
| `/check <processo>` | Verifica no SEI agora (respeita o intervalo mínimo, padrão de 5 min). |
| `/history <processo>` | Últimas mudanças detectadas. |
| `/pause <processo>` / `/resume <processo>` | Pausa ou retoma os alertas **só para você** (ou para o grupo). |
| `/unwatch <processo>` | Para de monitorar. |
| `/start`, `/help` | Apresentação e lista de comandos. |

**Regras:**
- Cada conversa acompanha até 10 processos (`TELEGRAM_MAX_PROCESSES_PER_CHAT`).
- Em grupos, só administradores usam `/watch`, `/unwatch`, `/pause` e `/resume`.
- Comandos no formato `/comando@NomeDoBot` também funcionam.

---

## Arquitetura

```mermaid
flowchart LR
    TG[Telegram] -- webhook HTTPS --> WEB
    subgraph Render
        WEB[Web Service<br/>Gunicorn + Django<br/>webhook · painel · admin]
        WORKER[Background Worker<br/>run_worker]
        DB[(PostgreSQL 18)]
    end
    WEB <--> DB
    WORKER <--> DB
    WORKER -- consultas públicas --> SEI[SEI/CADE]
    WORKER -- mensagens e documentos --> TG
```

| Peça | Papel |
|---|---|
| **Web Service** | Recebe as mensagens do bot (`/telegram/webhook/`, validado por secret e idempotente) e responde na hora. Também serve o painel web e o Django Admin. **Nunca consulta o SEI.** |
| **Background Worker** (`run_worker`) | A cada ciclo, na ordem: executa os pedidos do bot que dependem do SEI (primeira leitura, `/check`, `/last_update`), verifica os processos vencidos e envia as notificações pendentes, com retentativa. Publica o menu de comandos do bot ao iniciar. |
| **PostgreSQL 18** | Banco principal (`DATABASE_URL`). Em dev e testes, o SQLite local é usado automaticamente. |

| Camada | Tecnologia |
|---|---|
| Backend | Django 5.2, monolito com apps por domínio |
| Banco | PostgreSQL 18 (produção) / SQLite (dev e testes) |
| Canal principal | Telegram Bot API, via stdlib, sem SDK |
| Canais opcionais | E-mail (SMTP) e WhatsApp (Evolution API) |
| Interface | Django templates + CSS próprio, Django Admin |
| Execução | Gunicorn (1 worker, 2 threads) + `run_worker` |
| Deploy | Docker no Render (ou Docker Compose) |

---

## Deploy no Render

1. **Banco:** crie um PostgreSQL 18 (região Oregon, por exemplo).
2. **Env Group `cade-monitor`:** cadastre as variáveis de [Configuração](#configuração).
   Use a *Internal Database URL* em `DATABASE_URL`.
3. **Web Service:** use o Docker deste repositório, na mesma região do banco, vinculado ao Env
   Group, com o health check em `/admin/login/`. O `CMD` do `Dockerfile` já aplica as
   migrations e sobe o Gunicorn na `$PORT`.
4. **Background Worker:** use a mesma imagem e o mesmo Env Group, com o Docker Command
   `python manage.py run_worker`.
5. **Primeiro acesso:** crie o usuário do painel com `python manage.py createsuperuser` (pelo
   Shell do Render ou pela sua máquina, com a *External Database URL*).
6. **Ligar o bot:** rode `python manage.py telegram_webhook` e confira com `--info`.

> Workers e Cron Jobs não têm plano gratuito no Render. Um Web Service gratuito "dorme" após
> ~15 min sem acesso, e instâncias gratuitas podem ter as portas SMTP bloqueadas (confira a
> documentação do Render antes de ligar o e-mail).

---

## Configuração

Referência completa, com comentários, em [`.env.example`](.env.example). Nunca versione `.env`
nem `.env.*`.

**Núcleo**

| Variável | Exemplo / padrão | Observação |
|---|---|---|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(50))"` | Obrigatória com `DEBUG=false`. |
| `DEBUG` | `false` | |
| `ALLOWED_HOSTS` | `seu-app.onrender.com` | |
| `BASE_URL` | `https://seu-app.onrender.com` | Usada pelo webhook e pelo CSRF atrás do proxy. |
| `DATABASE_URL` | `postgresql://user:senha@host/db` | Ausente = SQLite. Definida mas vazia = erro. |
| `DB_SSLMODE` / `DB_CONN_MAX_AGE` | `require` / `60` | |

**Telegram**

| Variável | Padrão | Observação |
|---|---|---|
| `TELEGRAM_ENABLED` | `false` | Ligue no Web Service e no Worker. |
| `TELEGRAM_BOT_TOKEN` | — | Gerado no [@BotFather](https://t.me/BotFather). |
| `TELEGRAM_WEBHOOK_SECRET` | — | De 16 a 256 caracteres `[A-Za-z0-9_-]`. |
| `TELEGRAM_BOT_USERNAME` | vazio | Sem `@`. Se vazio, é obtido via `getMe`. |
| `TELEGRAM_MAX_PROCESSES_PER_CHAT` | `10` | |
| `TELEGRAM_CHECK_COOLDOWN_SECONDS` | `300` | Intervalo mínimo do `/check` (mínimo 60). |
| `TELEGRAM_HISTORY_LIMIT` | `5` | |
| `TELEGRAM_ATTACHMENT_MAX_BYTES` | `20971520` | Até 50 MB são aceitos pela Bot API. |

**Monitoramento**

| Variável | Padrão | Observação |
|---|---|---|
| `USER_AGENT` | — | Identifique o robô com um contato real. |
| `CHECK_INTERVAL_SECONDS` | `1500` | Mínimo de 25 min por processo. |
| `WORKER_TICK_SECONDS` | `5` | Tempo de resposta dos pedidos do bot. |
| `MAX_PROCESSES_PER_CYCLE` / `SLEEP_BETWEEN_REQUESTS_SECONDS` | `20` / `2` | |

**Canais opcionais**
- **E-mail:** `SMTP_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
  `SMTP_TLS`/`SMTP_SSL`, `MAIL_FROM`. Funciona com qualquer provedor SMTP (Gmail, Zoho, Outlook,
  Brevo, SES…). Na porta 587 use TLS; na 465, SSL. Sem SMTP, o e-mail sai no console em dev.
- **WhatsApp:** `EVOLUTION_ENABLED`, `EVOLUTION_API_BASE_URL`, `EVOLUTION_API_KEY`,
  `EVOLUTION_INSTANCE_NAME`. Provider único: [Evolution API](https://doc.evolution-api.com/)
  self-hosted.

---

## Painel web

O painel fica em `https://seu-app.onrender.com/` (login do Django). Nele você pode:
- cadastrar processos e assinantes de e-mail e WhatsApp;
- disparar "Checar agora" e "Enviar última atualização";
- revisar e classificar mudanças;
- ver o histórico de notificações.

No **Django Admin** (`/admin/`) estão os chats do Telegram, as ações do bot e as assinaturas
(inclusive as pausadas).

Processos criados pelo bot são pausados automaticamente quando ninguém mais os acompanha.
Processos cadastrados pelo painel nunca têm o status alterado pelo bot.

---

## Desenvolvimento local

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env                # sem DATABASE_URL → usa SQLite

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver          # painel em http://localhost:8000
python manage.py run_worker         # em outro terminal
```

- **Testar contra PostgreSQL:** `docker compose --profile pg up -d postgres` e
  `DATABASE_URL=postgresql://cade:cade@localhost:5432/cade?sslmode=disable`. Não rode a suíte
  contra o banco do Render.
- **Webhook em dev:** o Telegram exige HTTPS. Use um túnel e
  `python manage.py telegram_webhook --url https://seu-tunel`.

### Management commands

```bash
python manage.py run_worker                 # worker contínuo (--once = um ciclo)
python manage.py telegram_webhook           # registra webhook + menu (--info, --delete, --url)
python manage.py check_process --id 1       # checa um processo
python manage.py check_processes            # checa os vencidos (para cron)
python manage.py probe_process "08700.005905/2026-38"   # testa a extração sem gravar
python manage.py resolve_process "08700.005905/2026-38" # número → URL pública
python manage.py send_pending_notifications
python manage.py generate_daily_digest      # resumo diário (--hours 48 --dry-run)
python manage.py cleanup_snapshots          # snapshots antigos + registros do bot > 30 dias
python manage.py backup_db --dest backups   # SQLite: cópia; Postgres: pg_dump, se houver
```

### Migrar dados de SQLite para PostgreSQL

Com o worker **parado**:

```bash
# 1. exportar do SQLite (sem DATABASE_URL no ambiente)
python manage.py dumpdata --natural-foreign \
  --exclude contenttypes --exclude auth.permission \
  --exclude admin.logentry --exclude sessions \
  -o data/migration.json

# 2. importar no Postgres (com DATABASE_URL = External URL)
python manage.py migrate
python manage.py loaddata data/migration.json

# 3. reajustar as sequences
python manage.py sqlsequencereset processes subscribers monitoring notifications telegram_bot auth \
  | python manage.py dbshell
```

Depois, **apague `data/migration.json`**, porque ele contém dados de assinantes. O roteiro de
validação está em `specs/005-postgres-render/quickstart.md`.

---

## Estrutura

```
config/            settings, urls, validação do ambiente (env_schema), seleção do banco
apps/
  telegram_bot/    webhook, comandos, cliente da Bot API, ações executadas pelo worker
  processes/       MonitoredProcess (painel e bot)
  monitoring/      scraping do SEI, snapshots, diff, detecção de mudanças, run_worker
  notifications/   fila de notificações e canais: telegram, email, evolution
  subscribers/     assinantes e assinaturas (com pausa por assinatura)
  dashboard/       painel web
specs/             specs, planos e tarefas por feature (Spec Kit)
tests/             suíte automatizada (SQLite e PostgreSQL 18 no CI)
```

---

## Testes e CI

```bash
python manage.py test tests
```

O GitHub Actions roda a suíte duas vezes: com SQLite e contra um PostgreSQL 18 real (job
`test-postgres`), além de checar se falta alguma migration. As chamadas externas (SEI, Bot API,
SMTP, Evolution) são sempre mockadas.

---

## Como o projeto é desenvolvido

O projeto segue o [Spec Kit](https://github.com/github/spec-kit) (Spec-Driven Development). Cada
feature tem spec, plano, pesquisa, contratos e tarefas em `specs/NNN-nome/`. Os princípios
arquiteturais, como monitoramento responsável, monolito Django, PostgreSQL, Telegram sem SDK e
nada de over-engineering, estão em
[`.specify/memory/constitution.md`](.specify/memory/constitution.md).

| Feature | Conteúdo |
|---|---|
| `001-cade-monitor` | Base: monitoramento, diff, painel, e-mail/WhatsApp |
| `002-repo-hardening-cleanup` | Segurança, CI, dependências fixadas |
| `005-postgres-render` | PostgreSQL 18 como banco principal |
| `006-telegram-bot` | Bot do Telegram, alertas com documento, `/last_update` |
| `003`, `004` | Processos relacionados e confiabilidade operacional (ver `specs/`) |

---

## Uso responsável

- Intervalo mínimo de **25 minutos** por processo. O `/check` tem intervalo próprio, e pedidos
  simultâneos viram uma única consulta.
- Só HTTP público. O robô se identifica pelo `USER_AGENT`.
- Credenciais (banco, token do bot, SMTP) ficam só em variáveis de ambiente. Se alguma vazar,
  rotacione no provedor.
