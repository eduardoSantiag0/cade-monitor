# Implementation Plan: Hardening e Limpeza Técnica do Repositório

**Branch**: `002-repo-hardening-cleanup` | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-repo-hardening-cleanup/spec.md`

## Summary

Restaurar a higiene e a segurança básica do repositório (parar de versionar dados binários do
Postgres, restaurar o README, endurecer `SECRET_KEY`), remover código legado duplicado
(`cademon/`, `wa-bot/`), tornar o build reprodutível e verificado (pin de dependências + CI),
e eliminar duas dívidas de qualidade já confirmadas em código (duplicação em
`apps/processes/views.py`, download desnecessário de anexo no canal WhatsApp), adicionando
rastreamento de erros externo para o worker/scheduler. Abordagem técnica: mudanças cirúrgicas
dentro da arquitetura Django monolítica já existente, sem novos serviços de runtime — apenas
ferramentas de tempo de build/CI e uma dependência de observabilidade (SDK de rastreamento de
erros), justificada abaixo.

## Technical Context

**Language/Version**: Python 3.11 (ambiente de desenvolvimento atual, `.venv`) / imagem de produção `python:3.12-slim` (Dockerfile) — ambas suportadas por Django 5.2.

**Primary Dependencies**: Django 5.2.15, pydantic 2.x (`config/env_schema.py`, `apps/*/schemas.py`), python-dotenv, whitenoise, gunicorn (produção), redis (cliente opcional — ver Constitution Check). Nova dependência proposta: SDK de rastreamento de erros (ex.: `sentry-sdk`), para atender FR-010.

**Storage**: SQLite com WAL mode (banco principal da aplicação, decisão permanente do Princípio IV). Nenhuma mudança de storage nesta feature.

**Testing**: `python manage.py test tests` (Django `TestCase`/`SimpleTestCase`), suíte já existente em `tests/` (~1400 linhas). Esta feature adiciona execução automática dessa suíte via CI (FR-007) e cobertura para o fallback de cache (FR-011), sem trocar o framework de testes.

**Target Platform**: Linux (containers Docker via `docker-compose.yml`), rodando em VM com 1–2 vCPUs / ≤512MB RAM para o processo Django (Princípio I).

**Project Type**: Aplicação web monolítica Django (server-rendered, sem frontend separado).

**Performance Goals**: Não aplicável a esta feature — é hardening/qualidade, não introduz caminho de execução crítico novo. Único cuidado de performance explícito: FR-009 deve *reduzir* bytes transferidos por envio de anexo WhatsApp, não aumentar.

**Constraints**: Deve caber nos limites de recurso do Princípio I (sem novo processo daemon de longa duração); qualquer nova dependência Python precisa de justificativa escrita (Princípio VIII) — ver Complexity Tracking.

**Scale/Scope**: Repositório único, ~10 apps/módulos afetados (config, apps/processes, apps/monitoring, apps/notifications, cademon [remoção], wa-bot [remoção], Makefile, requirements.txt, .github/workflows [novo]). Sem mudança de escala de dados ou de usuários.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Avaliação contra `.specify/memory/constitution.md` v1.1.0:

| Princípio | Relevante? | Avaliação |
|---|---|---|
| I. Simplicidade Operacional | Sim | ✅ Não adiciona processos/daemons. A única dependência nova (SDK de erro) é justificada em Complexity Tracking, com verba explícita de baixo consumo de recursos. Exceção do Redis (v1.1.0) é apenas documentada (FR-011), não expandida. |
| II. Monitoramento Responsável | Não diretamente | ✅ Nenhum FR desta spec altera cadência de scraping, autenticação ou coleta de dados pessoais. |
| III. Django Monolítico Bem Organizado | Sim | ✅ FR-008 (refatoração das views duplicadas) move lógica repetida das views para uma função de serviço compartilhada, reforçando — não violando — a separação `views.py` fino / lógica em `services.py`. |
| IV. SQLite em Produção | Não | ✅ Não alterado. |
| V. Notificações via Evolution API e SMTP | Sim | ✅ FR-009 muda *como* o anexo é validado antes do envio, não introduz novo provedor de mensageria. |
| VI. Humanização das Mensagens | Não diretamente | ✅ Sem mudança de conteúdo de mensagem. |
| VII. Portfólio-Ready — Qualidade de Código | Sim | ✅ Esta feature é, em essência, a aplicação direta deste princípio: testes, tratamento de erro, logs estruturados, rastreamento de erro (FR-010) e higiene de repositório. |
| VIII. Sem Over-Engineering | Sim | ⚠️ Requer justificativa escrita para a nova dependência (SDK de rastreamento de erros) e para a introdução de CI — ver Complexity Tracking abaixo. Nenhum REST API, GraphQL, fila pesada ou frontend SPA é introduzido. |

**Resultado do gate (pré-Fase 0)**: PASS, condicionado às justificativas registradas em Complexity Tracking (Princípio VIII exige isso por escrito antes de adicionar a dependência — não impede o gate, apenas exige o registro).

**Re-check pós-Fase 1 (pós-design)**: PASS sem novidades. O desenho de Fase 0/1 (`research.md`,
`data-model.md`) não introduziu nenhuma dependência, serviço ou padrão além dos dois já
registrados em Complexity Tracking (`sentry-sdk`, GitHub Actions). Em particular: FR-009 (Redis
research item 6) resultou em **remover** uma chamada existente, não adicionar; FR-006 (pin de
dependências) foi resolvido sem ferramenta nova (item 3 do research). Nenhum novo gate violado.

## Project Structure

### Documentation (this feature)

```text
specs/002-repo-hardening-cleanup/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md         # Phase 1 output (/speckit.plan command)
├── quickstart.md         # Phase 1 output (/speckit.plan command)
└── tasks.md              # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

Nenhum diretório `contracts/` é gerado: esta feature não expõe nem consome nenhuma interface
externa nova (sem API pública, sem endpoint novo) — apenas altera código interno, configuração
de repositório e pipeline de CI.

### Source Code (repository root)

Projeto único (monolito Django), estrutura já existente — nenhuma reestruturação de diretórios é
necessária. Trechos relevantes para esta feature:

```text
config/
├── settings.py            # FR-003: validação estrita de SECRET_KEY em produção
├── env_schema.py           # FR-003: regra de validação (Pydantic) para SECRET_KEY/DEBUG
└── sentry.py                # NOVO — inicialização opcional do SDK de erro (FR-010)

apps/
├── processes/
│   ├── views.py             # FR-008: extrair helper compartilhado de envio manual
│   └── services.py          # FR-008: novo helper de despacho por assinante/canal
├── monitoring/
│   ├── cache.py              # FR-011: cobertura de teste do fallback sem Redis
│   └── management/commands/run_worker.py   # FR-010: captura de exceção não tratada
├── notifications/
│   └── services.py           # FR-009: parar de baixar anexo binário p/ WhatsApp sem necessidade

cademon/                      # FR-004: REMOVIDO nesta feature
wa-bot/                       # FR-004: REMOVIDO nesta feature
tests/
└── test_scraper.py           # FR-004: REMOVIDO (só testava cademon/scraper.py)

.github/
└── workflows/
    └── ci.yml                # NOVO — FR-007: roda `manage.py test` em push/PR

Makefile                      # FR-005: remover bloco duplicado
requirements.txt              # FR-006: pin de versões exatas diretamente no arquivo (sem lockfile separado — ver research.md item 3)
.gitignore                    # FR-001: adicionar data/evolution-postgres/
README.md                     # FR-002: restaurado/recriado
data/evolution-postgres/      # FR-001: removido do índice do git (git rm -r --cached), continua no disco
```

**Structure Decision**: Nenhuma nova app Django é criada. As mudanças de FR-008/FR-009 ficam
dentro das apps de domínio já existentes (`processes`, `notifications`), respeitando o
Princípio III (lógica de negócio em `services.py`, views finas). O SDK de rastreamento de erros
(FR-010) ganha um módulo de inicialização dedicado (`config/sentry.py`) importado no `settings.py`,
em vez de código de inicialização espalhado — mantém `settings.py` legível.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Nova dependência Python: SDK de rastreamento de erros (ex. `sentry-sdk`) — Princípio VIII exige justificativa escrita para qualquer nova dependência | FR-010 exige que falhas não tratadas do worker/scheduler cheguem a um lugar consultável fora do log local; hoje elas só existem em `logs/cade-monitor.log`, que ninguém monitora ativamente. Sem isso, o próprio objetivo desta spec (parar de descobrir problemas tarde demais) fica incompleto. | Alternativa mais simples considerada: apenas melhorar o log estruturado local. Rejeitada porque não resolve o problema real (ninguém lê o log até um assinante reclamar) — a spec 004 (confiabilidade operacional) já assume a existência de um canal de erro externo para seus próprios alertas, então adiar essa dependência só empurraria o mesmo custo para depois. |
| Novo pipeline de CI (`.github/workflows/ci.yml`) — não é uma dependência Python, mas é uma peça nova de infraestrutura de projeto | FR-007 exige que a suíte de testes já existente rode automaticamente; hoje ela só roda se alguém lembrar de digitar `make test`. | Alternativa considerada: hook de pre-commit local. Rejeitada porque não protege contra alguém pular o hook nem contra revisão de PR — o objetivo é um gate visível no Pull Request, não apenas uma conveniência local. |
