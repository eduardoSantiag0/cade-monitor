<!--
  SYNC IMPACT REPORT
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
- MUST NOT: Introduzir serviços de fila (Celery, RQ, Dramatiq) ou cache distribuído (Redis,
  Memcached).

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

- MUST: Apps de domínio: `processes`, `monitoring`, `notifications`, `subscribers`, `dashboard`.
- MUST: Lógica de negócio em `services.py`; queries reutilizáveis em `selectors.py`.
- MUST: Views apenas orquestram: validam entrada, chamam service, retornam resposta.
- MUST NOT: Colocar lógica de negócio em models, views ou templates.
- MUST NOT: Criar microserviços, APIs REST autônomas ou separar o projeto em múltiplos repositórios.

### IV. SQLite em Produção

O banco de dados de produção É SQLite com WAL mode ativado. Esta é uma escolha deliberada e
permanente para o escopo do projeto.

- MUST: Ativar WAL mode via signal `connection_created` no `MonitoringConfig.ready()`.
- MUST: Persistir o arquivo SQLite em volume Docker mapeado para o host.
- MUST: Manter um único worker sequencial para evitar contention de escrita.
- MUST NOT: Introduzir PostgreSQL, MySQL, ou qualquer banco servidor como dependência de produção.
- MUST NOT: Usar múltiplos workers Django que escrevam no banco simultaneamente.

### V. Notificações via Evolution API (WhatsApp) e SMTP

O canal de notificação WhatsApp DEVE usar exclusivamente a Evolution API self-hosted. E-mail DEVE
usar `django.core.mail` com backend SMTP configurável.

- MUST: Implementar canais como classes em `notifications/channels/` com interface comum.
- MUST NOT: Usar qualquer outro provedor de mensageria fora da Evolution API.
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

## Tech Stack Canônico

Esta stack É o contrato de implementação. Desvios MUST ser aprovados via emenda à constituição.

| Camada    | Tecnologia                      | Restrição                           |
| --------- | ------------------------------- | ----------------------------------- |
| Backend   | Django 5.x                      | Monolito, sem DRF obrigatório       |
| Banco     | SQLite (WAL)                    | Volume Docker; sem servidor externo |
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

**Version**: 1.0.0 | **Ratified**: 2026-07-07 | **Last Amended**: 2026-07-07
