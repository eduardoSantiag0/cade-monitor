<!--
  SYNC IMPACT REPORT
  Version change: 1.1.0 → 2.0.0 (MAJOR)

  Modified principles:
    - I. Simplicidade Operacional — webhook do Telegram roda dentro do Gunicorn existente;
      ações pesadas do bot são executadas pelo `run_worker` via tabela no banco (não é fila).
    - III. Django Monolítico Bem Organizado — novo app de domínio `telegram_bot`.
    - IV. "SQLite em Produção" → "PostgreSQL em Produção" (redefinição incompatível):
      PostgreSQL 18 gerenciado (Render) via `DATABASE_URL`; SQLite restrito a dev/testes.
    - V. "Notificações via Evolution API (WhatsApp) e SMTP" → "Notificações via Telegram,
      Evolution API e SMTP": Telegram Bot API passa a ser o canal principal.
    - VIII. Sem Over-Engineering — registra justificativa da dependência `psycopg[binary]`.
  Modified sections: Tech Stack Canônico (Banco, Mensageria, dependências).
  Added sections: None
  Removed sections: None
  Rationale: Features 005-postgres-render e 006-telegram-bot. O dono do projeto decidiu
    tornar o Telegram o canal principal de comunicação com usuários (autoatendimento via
    comandos) e usar PostgreSQL 18 no Render como banco principal.
  Templates requiring updates:
    ✅ .specify/memory/constitution.md — this file
    ✅ .specify/templates/plan-template.md — gates são derivados da constituição; sem mudança
    ✅ .specify/templates/spec-template.md — sem mudanças necessárias
    ✅ .specify/templates/tasks-template.md — sem mudanças necessárias
    ✅ README.md — stack e configuração de banco atualizadas (feature 005)
    ⚠ README.md — seção do Telegram pendente (feature 006)
    ✅ .env.example — DATABASE_URL/DB_* documentadas (feature 005)
    ⚠ .env.example — TELEGRAM_* pendentes (feature 006)
  Deferred TODOs: None
-->

<!--
  SYNC IMPACT REPORT (histórico)
  Version change: 1.0.0 → 1.1.0

  Modified principles:
    - I. Simplicidade Operacional — adicionada exceção explícita permitindo Redis
      como cache opcional de hash de processo (já implementado em código antes
      desta emenda; a emenda documenta a realidade em vez de mudar o código).
  Added sections: None
  Removed sections: None
  Rationale: Auditoria de código (spec 002-repo-hardening-cleanup) encontrou uso
    de Redis (PROCESS_HASH_REDIS_*) em produção contradizendo o texto original
    do Princípio I ("MUST NOT: ... cache distribuído (Redis, Memcached)"). Dono
    do projeto decidiu manter o Redis (ganho de performance sob muitos
    processos monitorados) e formalizar a exceção em vez de removê-lo.
  Templates requiring updates:
    ✅ .specify/memory/constitution.md — this file
    ⚠ .specify/templates/plan-template.md — nenhuma mudança estrutural necessária;
      novos planos que usem cache distribuído devem citar esta exceção no
      Constitution Check em vez de tratá-la como violação.
    ✅ .specify/templates/spec-template.md — sem mudanças necessárias
    ✅ .specify/templates/tasks-template.md — sem mudanças necessárias
  Deferred TODOs: None
-->

<!--
  SYNC IMPACT REPORT (histórico)
  Version change: (unversioned template) → 1.0.0
  This is the initial ratification — all sections created from scratch.

  Modified principles: N/A (first version)
  Added sections: Core Principles (8), Tech Stack, Development Workflow, Governance
  Removed sections: None
  Templates requiring updates:
    ✅ .specify/memory/constitution.md — this file
    ✅ .specify/templates/plan-template.md — Constitution Check gates align with principles below
    ✅ .specify/templates/spec-template.md — no changes required; structure is compatible
    ✅ .specify/templates/tasks-template.md — no changes required; task phases are compatible
  Deferred TODOs: None
-->

# CADE Monitor Constitution

## Core Principles

### I. Simplicidade Operacional

A aplicação DEVE rodar confortavelmente em uma VM com 1–2 vCPUs e ≤ 512 MB de RAM disponível para
o processo Django. Toda decisão arquitetural DEVE ser avaliada pelo critério de consumo de
CPU/memória em idle e sob carga típica (dezenas de processos monitorados).

- MUST: Minimizar dependências de runtime; stdlib Python é preferida para scraping e utilitários.
- MUST: Um único processo Gunicorn com 1 worker e 2 threads.
- MUST: Worker contínuo implementado como management command (`run_worker`), sem daemons externos.
- MUST NOT: Introduzir serviços de fila (Celery, RQ, Dramatiq).
- MAY: Usar Redis exclusivamente como cache opcional de hash de processo
  (`PROCESS_HASH_REDIS_*`), como otimização de performance sob muitos processos monitorados.
  Esta é a única exceção de cache distribuído permitida nesta constituição.
  - MUST: A aplicação MUST permanecer funcional com esse cache desabilitado
    (`PROCESS_HASH_REDIS_ENABLED=false`), usando o hash já persistido em
    `MonitoredProcess.last_hash` como fallback — Redis nunca é fonte única de verdade.
  - MUST NOT: Usar Redis para qualquer outra finalidade (fila, sessão, cache de página,
    pub/sub) sem nova emenda a este princípio.
- MUST: O webhook do Telegram é uma view no Gunicorn existente — nenhum processo extra para o bot.
- MUST: Ações do bot que consultam o SEI (primeira leitura do `/watch`, `/check`) são gravadas
  numa tabela do banco e executadas pelo `run_worker`, no mesmo padrão das notificações
  pendentes. O webhook MUST responder rápido e NUNCA fazer scraping no request.

### II. Monitoramento Responsável

O sistema DEVE consultar apenas páginas públicas do CADE/SEI e respeitar uma cadência mínima de
**25 minutos por processo**. O intervalo padrão configurável DEVE ser ≥ 30 minutos.

- MUST: Usar apenas HTTP GET em endpoints públicos e sem autenticação.
- MUST NOT: Burlar mecanismos de autenticação, capturar sessões, ou armazenar dados pessoais de
  partes dos processos além do número e URL públicos.
- MUST NOT: Realizar requisições paralelas sem controle de rate (no burst de scraping).
- SHOULD: Logar toda requisição de scraping com timestamp, URL e resultado para auditoria.

### III. Django Monolítico Bem Organizado

A aplicação segue uma arquitetura Django monolítica com apps separados por domínio. A lógica de
negócio reside em `services.py`; consultas complexas em `selectors.py`. Views são finas.

- MUST: Apps de domínio: `processes`, `monitoring`, `notifications`, `subscribers`, `dashboard`,
  `telegram_bot`.
- MUST: Lógica de negócio em `services.py`; queries reutilizáveis em `selectors.py`.
- MUST: Views apenas orquestram: validam entrada, chamam service, retornam resposta.
- MUST NOT: Colocar lógica de negócio em models, views ou templates.
- MUST NOT: Criar microserviços, APIs REST autônomas ou separar o projeto em múltiplos repositórios.

### IV. PostgreSQL em Produção

O banco de dados de produção É PostgreSQL 18 gerenciado (Render), configurado exclusivamente via
`DATABASE_URL`. SQLite permanece como fallback para desenvolvimento local e testes quando
`DATABASE_URL` não está definida.

- MUST: Credenciais do banco apenas em variável de ambiente (`DATABASE_URL`); NUNCA no repositório.
- MUST: Conexões ao Postgres externas ao Render usam TLS (`sslmode=require`).
- MUST: Código e migrations portáveis entre PostgreSQL e SQLite (sem SQL específico de vendor
  fora de pontos isolados e condicionados a `connection.vendor`).
- MUST: PRAGMAs/WAL aplicados somente quando `connection.vendor == 'sqlite'`.
- MUST: Manter um único worker sequencial de monitoramento.
- MUST NOT: Usar SQLite como banco de produção.
- MUST NOT: Introduzir um segundo banco servidor (MySQL, MongoDB etc.) além do PostgreSQL.

### V. Notificações via Telegram, Evolution API (WhatsApp) e SMTP

O Telegram É o canal principal de comunicação com usuários, tanto para comandos (autoatendimento)
quanto para alertas. WhatsApp via Evolution API self-hosted e e-mail via `django.core.mail`
(SMTP) permanecem como canais opcionais.

- MUST: Chamar a Telegram Bot API por HTTP com stdlib (`urllib`), sem SDK de terceiros.
- MUST: Validar o webhook do Telegram pelo header `X-Telegram-Bot-Api-Secret-Token` e tratar
  updates de forma idempotente (`update_id`).
- MUST: Implementar canais em `notifications/channels/` com interface comum
  (`(status, error)`).
- MUST NOT: Usar provedor de WhatsApp diferente da Evolution API.
- MUST NOT: Adicionar dependências de SDK proprietário para envio de mensagens.
- SHOULD: Registrar cada tentativa de envio em `NotificationAttempt` para rastreabilidade.

### VI. Humanização das Mensagens

Notificações e diffs DEVEM ser apresentados em linguagem natural, em português, legíveis por não
técnicos. Mudanças detectadas DEVEM ser classificáveis por revisores humanos.

- MUST: Mensagens de notificação escritas em linguagem natural (não dumps de JSON/HTML).
- MUST: Diff estruturado separando andamentos e protocolos; destacar apenas o que mudou.
- MUST: Suportar classificação humana de mudanças: `analisado`, `importante`, `ignorado`,
  `falso_positivo`.
- MUST NOT: Enviar notificações automaticamente sem ao menos um ciclo de detecção de mudança
  confirmado.

### VII. Portfólio-Ready — Qualidade de Código

O código DEVE estar em nível de qualidade adequado para demonstração pública e revisão técnica.

- MUST: Testes automatizados cobrindo services, selectors, scraping e notificações.
- MUST: Management commands com `--help` descritivo e tratamento de erros robusto.
- MUST: Logs estruturados com nível (`DEBUG`/`INFO`/`WARNING`/`ERROR`) e contexto (process ID,
  URL).
- MUST: Tratamento explícito de exceções de rede, parsing e envio de notificações (sem silêncio
  de erros).
- SHOULD: Cobertura de testes ≥ 80% nos módulos `services.py` e `selectors.py`.

### VIII. Sem Over-Engineering

A complexidade introduzida DEVE ser justificada pelo problema que resolve. O padrão é: não
adicionar.

- MUST NOT: Kubernetes, orquestração de containers além de Docker Compose.
- MUST NOT: Frontend SPA (React, Vue, Angular); templates Django são suficientes.
- MUST NOT: Mensageria pesada (Kafka, RabbitMQ, SQS) ou múltiplos workers.
- MUST NOT: GraphQL, REST API pública, ou camada BFF enquanto não houver cliente externo.
- MUST: Justificar por escrito qualquer nova dependência Python antes de adicioná-la ao projeto.
  - `psycopg[binary]` (v3): driver PostgreSQL oficialmente suportado pelo Django; não há
    alternativa em stdlib. A URL do banco é parseada com `urllib.parse` para evitar
    `dj-database-url`.

## Tech Stack Canônico

Esta stack É o contrato de implementação. Desvios MUST ser aprovados via emenda à constituição.

| Camada    | Tecnologia                      | Restrição                           |
| --------- | ------------------------------- | ----------------------------------- |
| Backend   | Django 5.x                      | Monolito, sem DRF obrigatório       |
| Banco     | PostgreSQL 18 (Render)          | Via `DATABASE_URL`; driver psycopg3 |
| Banco dev | SQLite (WAL)                    | Somente dev/testes                  |
| Telegram  | Telegram Bot API (webhook)      | Canal principal; HTTP via stdlib    |
| Frontend  | Django Templates + CSS próprio  | Sem frameworks JS                   |
| Worker    | `run_worker` management command | Loop com sleep; sem Celery          |
| WSGI      | Gunicorn 1 worker 2 threads     | Sem uvicorn/asgi em prod            |
| Static    | WhiteNoise                      | Sem Nginx para static em dev        |
| WhatsApp  | Evolution API (self-hosted)     | Provider unico permitido            |
| E-mail    | django.core.mail (SMTP)         | Sem SendGrid/Mailgun SDK            |
| Container | Docker + Docker Compose         | Sem Kubernetes                      |

## Development Workflow

1. **Mudanças de modelo** MUST gerar migration antes de qualquer PR/merge.
2. **Novos services** MUST ter ao menos um teste unitário cobrindo o caminho feliz e um caso de
   erro.
3. **Scrapers/extractors** MUST ser testados com fixtures HTML locais (sem HTTP ao testar).
4. **Variáveis de ambiente** MUST ser documentadas no `.env.example`; nunca hardcoded.
5. **Commits** SHOULD seguir Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
6. **Constitution Check** MUST ser executado mentalmente antes de qualquer novo serviço,
   dependência, ou decisão arquitetural.

## Governance

Esta constituição É a fonte de verdade arquitetural para o CADE Monitor. Ela SUPERSEDE comentários
de código, READMEs parciais e decisões verbais.

**Processo de emenda**:

1. Propor a mudança com justificativa técnica e impacto no escopo.
2. Atualizar este arquivo com versão incrementada seguindo semver:
    - MAJOR: Remoção ou redefinição incompatível de princípio.
    - MINOR: Adição de princípio ou seção com impacto real.
    - PATCH: Clarificação, correção de redação, refinamento semântico menor.
3. Verificar consistência com templates em `.specify/templates/`.
4. Registrar data de emenda em `Last Amended`.

**Compliance**: Todo plano de feature DEVE incluir uma seção "Constitution Check" verificando
alinhamento com os Princípios I–VIII antes de iniciar implementação.

**Version**: 2.0.0 | **Ratified**: 2026-07-07 | **Last Amended**: 2026-09-22
