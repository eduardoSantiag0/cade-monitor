# CADE Monitor

Radar leve de acompanhamento de processos públicos do CADE/SEI.
Avisa assinantes por e-mail ou WhatsApp quando houver nova movimentação ou qualquer alteração
relevante no texto extraído de uma página pública.

> O sistema apenas consulta páginas públicas, extrai conteúdo visível, compara com versões
> anteriores e registra mudanças. Não acessa dados privados, não burla autenticação e não
> modifica nenhuma informação.

---

## Stack

| Camada    | Tecnologia                     |
| --------- | ------------------------------ |
| Backend   | Django                         |
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
# Edite .env se necessário

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
```

---

## Páginas públicas suportadas

O sistema aceita dois formatos de fonte:

1. **URL pública direta** — qualquer `http://` ou `https://` acessível publicamente
2. **Número de protocolo CADE/SEI** — ex: `08700.005905/2026-38`

Quando fornecido o número, o sistema consulta a pesquisa pública do SEI e resolve
automaticamente para a URL de detalhe do processo.

---

## Variáveis de ambiente

Veja `.env.example` para a lista completa com comentários.
Variáveis obrigatórias em produção:

| Variável        | Descrição                                                                              |
| --------------- | -------------------------------------------------------------------------------------- |
| `SECRET_KEY`    | Chave Django — gere com `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `ALLOWED_HOSTS` | Domínios permitidos, separados por vírgula                                             |
| `SQLITE_PATH`   | Caminho do banco SQLite (use volume Docker persistente)                                |
| `DEBUG`         | `false` em produção                                                                    |

---

## Testes

```bash
python manage.py test tests
python manage.py test tests --verbosity=2
```

---

## Notas de segurança

- Não versione o arquivo `.env`
- Troque a `SECRET_KEY` antes de qualquer deploy
- Use HTTPS em produção (Nginx/Caddy na frente do Gunicorn)
- O painel exige autenticação Django em todas as rotas

Importante: voce colou credenciais de servidor na conversa. Troque essa senha no painel da hospedagem antes de colocar qualquer monitor em producao. Este projeto nao salva senha SSH e nao precisa dela no arquivo .env.

## Como funciona

- O painel web cadastra processos, URLs publicas ou numeros de processo/protocolo, e-mails e telefones.
- O worker consulta as paginas em intervalos curtos, por padrao 30 segundos.
- Na primeira leitura, o sistema grava uma linha de base e nao notifica.
- Nas leituras seguintes, se o texto publico extraido mudar, ele registra a movimentacao e dispara alertas.
- E-mail usa SMTP configurado por variaveis de ambiente.
- WhatsApp e opcional via Meta WhatsApp Cloud API ou Twilio.

Nao existe push se a fonte e apenas uma pagina publica. O comportamento mais rapido e seguro e polling curto. Para algo realmente instantaneo, seria necessario um webhook/API oficial do orgao ou acesso a uma fonte que publique eventos em tempo real.

## Fonte CADE suportada

A pagina de pesquisa publica do CADE fica em:

    https://sei.cade.gov.br/sei/modulos/pesquisa/md_pesq_processo_pesquisar.php?acao_externa=protocolo_pesquisar&acao_origem_externa=protocolo_pesquisar&id_orgao_acesso_externo=0

O app aceita dois formatos no cadastro:

- Link final de exibicao do processo, como md_pesq_processo_exibir.php. Este e o melhor formato para monitorar.
- Numero do processo/protocolo, como 08700.005905/2026-38. Nesse caso o app envia uma consulta publica usando o campo txtProtocoloPesquisa e segue automaticamente o primeiro link Acessar para monitorar a pagina final.

Exemplo validado visualmente:

    Processo: 08700.005905/2026-38
    Link: https://sei.cade.gov.br/sei/modulos/pesquisa/md_pesq_processo_exibir.php?1MQnTNkPQ_sX_bghfgNtnzTLgP9Ehbk5UOJvmzyesnbE-Rf6Pd6hBcedDS_xdwMQMK6_PgwPd2GFLljH0OLyFWycTBhjBauP5dYFoUnRg02-3_TzC1t4QnSL57ciD1Ce

Nesse exemplo, a pagina contem Lista de Protocolos e Lista de Andamentos. O monitor compara o texto dessas areas dentro da pagina publica.

## Estrutura

    cademon/                aplicacao Python
    data/                   banco SQLite em producao local
    logs/                   logs dos processos
    scripts/                scripts simples para manter web e worker ativos
    tests/                  testes locais
    .env.example            modelo de configuracao

O MVP usa somente a biblioteca padrao do Python, para facilitar uso em servidor compartilhado.

## Rodar localmente no Windows

Na pasta do projeto:

    python -m venv .venv
    .venv\Scripts\activate
    copy .env.example .env
    python -m cademon init
    python -m cademon serve --host 127.0.0.1 --port 8000

Em outro terminal:

    .venv\Scripts\activate
    python -m cademon worker

Abra http://127.0.0.1:8000 e entre com ADMIN_USER e ADMIN_PASSWORD configurados no .env.

## Rodar no Linux ou Whatbox

    cd ~/apps/cade-monitor
    python3 -m venv .venv
    . .venv/bin/activate
    cp .env.example .env
    nano .env
    python -m cademon init
    python -m cademon serve --host 0.0.0.0 --port 8000

Em outro terminal:

    cd ~/apps/cade-monitor
    . .venv/bin/activate
    python -m cademon worker

A configuracao exata de porta publica ou proxy depende do painel da hospedagem. Se ela oferecer Passenger, reverse proxy ou app manager, aponte para o comando python -m cademon serve.

## Manter rodando com cron

Depois de testar manualmente, adicione no cron do servidor:

    * * * * * cd /home/SEU_USUARIO/apps/cade-monitor && sh scripts/keepalive_worker.sh
    * * * * * cd /home/SEU_USUARIO/apps/cade-monitor && HOST=0.0.0.0 PORT=8000 sh scripts/keepalive_web.sh

## Configurar e-mail

Use um provedor SMTP confiavel, por exemplo SMTP2GO, Mailgun, SendGrid, Amazon SES, Gmail com app password, ou o SMTP do seu dominio.

Campos principais no .env:

    SMTP_HOST=smtp.example.com
    SMTP_PORT=587
    SMTP_USER=usuario@example.com
    SMTP_PASSWORD=senha-ou-app-password
    MAIL_FROM=usuario@example.com
    SMTP_TLS=true

Sem SMTP configurado, a movimentacao fica registrada, mas a notificacao de e-mail aparece como skipped no banco.

## Configurar WhatsApp

WhatsApp proativo normalmente exige provedor oficial e, em muitos cenarios, modelo de mensagem aprovado. As duas opcoes previstas no MVP:

Meta WhatsApp Cloud API:

    WHATSAPP_PROVIDER=meta
    WHATSAPP_META_TOKEN=token
    WHATSAPP_META_PHONE_NUMBER_ID=id_do_numero

Twilio WhatsApp:

    WHATSAPP_PROVIDER=twilio
    TWILIO_ACCOUNT_SID=sid
    TWILIO_AUTH_TOKEN=token
    TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

Se a API retornar erro por template/sessao, o app registra a falha em notifications. Para producao, o proximo passo e implementar mensagens template aprovadas para o provedor escolhido.

## Cadastrar um processo

No painel:

1. Informe um nome interno.
2. Cole o link final publico do processo ou informe o numero, por exemplo 08700.005905/2026-38.
3. Informe e-mails e, se houver provedor configurado, telefones em formato internacional.
4. Clique em Cadastrar.
5. Clique em Checar para gravar a primeira leitura. A partir da proxima mudanca, o alerta e enviado.

## Cuidados de producao

- Use HTTPS no painel web.
- Troque ADMIN_PASSWORD e APP_SECRET_KEY.
- Use intervalos responsaveis. Muitas URLs em 10 segundos podem sobrecarregar paginas publicas.
- Prefira cadastrar o link final md_pesq_processo_exibir.php quando possivel.
- Valide a pagina oficial antes de tratar o alerta como prova processual.
- Monitore logs/worker.log e logs/web.log.
- Guarde backups do arquivo data/cade-monitor.sqlite3.

## Comandos uteis

    python -m cademon probe --url "https://pagina-publica"
    python -m cademon probe --url "08700.005905/2026-38"
    python -m cademon list
    python -m cademon check --id 1
    python -m unittest discover -s tests
