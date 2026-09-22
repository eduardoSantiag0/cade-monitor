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
| Banco     | SQLite (WAL mode)              |
| Interface | Django templates + CSS próprio |
| Admin     | Django Admin                   |
| Worker    | `management command` em loop   |
| WSGI      | Gunicorn                       |
| WhatsApp  | Evolution API                  |
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

# Backup do SQLite
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
  notifications/ ← Notification, canais email/evolution
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
| `SQLITE_PATH`   | Caminho do banco SQLite (use volume Docker persistente)                                |
| `DEBUG`         | `false` em produção                                                                    |

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
- Monitore `logs/cade-monitor.log` e faça backup regular do banco SQLite
  (`python manage.py backup_db`).
