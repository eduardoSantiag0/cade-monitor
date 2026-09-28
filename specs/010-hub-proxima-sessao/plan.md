# Implementation Plan: Próxima sessão de julgamento no dashboard

**Branch**: `010-hub-proxima-sessao` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-hub-proxima-sessao/spec.md`

## Summary

Um cartão no dashboard já existente (`apps/dashboard/`) mostra a próxima sessão de julgamento do
CADE (data + título) e, quando publicada, o link da pauta em PDF — dados vindos de duas páginas
públicas do CADE (`www.gov.br/cade/.../calendario-de-sessoes` e `www.gov.br/cade/.../sessoes de
julgamento/{ano}`, esta última linkando PDFs em `cdn.cade.gov.br`). A busca roda só em segundo
plano, dentro do `run_worker` já existente (nunca na view), com um cache TTL compartilhado entre
o processo web e o worker. Em vez de um modelo novo, o cache usa o backend `DatabaseCache` já
embutido no framework Django (`django.core.cache`) — atende exatamente ao requisito ("par
chave/valor com validade, compartilhado entre processos", FR-004/FR-005) sem nenhuma dependência
nova nem tabela desenhada à mão.

## Technical Context

**Language/Version**: Python 3.11 (Django 5.2.15).

**Primary Dependencies**: Django 5.2 (`django.core.cache`, backend `db`, já embutido — nenhuma
dependência nova); stdlib `urllib` para HTTP, mesmo padrão de `apps/monitoring/clients.py`.

**Storage**: Uma tabela de cache Django (`cache_hub`, criada por `python manage.py
createcachetable`), sem modelo Django próprio — é a tabela genérica do backend `DatabaseCache`.
Nenhuma migration de app a escrever à mão.

**Testing**: `django.test.TestCase`/`SimpleTestCase`, fixtures HTML locais para as duas páginas do
CADE, `unittest.mock.patch` para HTTP e para o cache (`django.core.cache.cache`).

**Target Platform**: Linux (Docker/Render), mesmo processo Gunicorn + worker único já existente.

**Project Type**: Web service (monolito Django) — sem app novo; a lógica entra em
`apps/dashboard/` (consumidor: a view) e um pequeno módulo de busca dentro do mesmo app.

**Performance Goals**: Leitura do cartão no dashboard é uma leitura de cache (O(1), sem HTTP);
atualização em segundo plano no máximo 1x por janela de cadência mínima por fonte.

**Constraints**: Sem dependência nova (Princípio VIII); sem HTTP na view (SC-001); mesma cadência
mínima entre tentativas já estabelecida como padrão do projeto (Princípio II, espírito da emenda
v2.2.0 — cadência por fonte, não por processo monitorado).

**Scale/Scope**: Dado global (não por assinante/processo) — 1 cartão, 2 chaves de cache, sem
relação com a escala de processos monitorados.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
|---|---|
| I. Simplicidade Operacional | **PASS** — sem processo/worker novo; atualização entra no `run_worker` existente; usa o backend de cache já embutido do Django em vez de infraestrutura nova. |
| II. Monitoramento Responsável | **PASS** — GET público sem auth às duas fontes; cadência mínima entre tentativas evita burst. **Interpretação registrada**: `www.gov.br/cade/...` é lido como "página pública do CADE" já em escopo (é o espaço oficial do CADE dentro do portal compartilhado `gov.br`, não uma fonte de terceiro — mesmo raciocínio já usado para `cdn.cade.gov.br`), então **não é necessária nova emenda** ao Princípio II para esta feature. Diferente do caso do DOU (feature 009), aqui não se trata de uma classe de fonte nova (outro órgão, outro diário oficial) — é o próprio CADE publicando em outro canto do mesmo portal do governo. |
| III. Django Monolítico Bem Organizado | **PASS** — lógica de busca/formatação em `apps/dashboard/hub.py` (`services`-like, funções puras + uma função de refresh), view continua fina (só lê o cache). |
| IV. PostgreSQL em Produção | **PASS** — `DatabaseCache` é portável Postgres/SQLite (tabela de cache padrão do Django), sem SQL específico de vendor. |
| V. Notificações | **N/A** — feature não envia notificação alguma. |
| VI. Humanização das Mensagens | **N/A** — sem mensagem automática; texto do cartão é estático/direto (data, título, link). |
| VII. Portfólio-Ready | **PASS** — testes com fixtures locais, sem HTTP real; falha de fonte tratada explicitamente (nunca silêncio, sempre "sem cartão" documentado). |
| VIII. Sem Over-Engineering | **PASS** — nenhuma dependência nova; escopo deliberadamente reduzido (spec.md, Assumptions) excluindo o que não serve a um painel interno autenticado (live YouTube, geo-IP) ou que duplicaria a futura feature de Agenda/Prazos. |

## Project Structure

### Documentation (this feature)

```text
specs/010-hub-proxima-sessao/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/dashboard/
├── hub.py                    # NOVO: busca (HTTP), parsing e refresh do cache (2 fontes)
├── views.py                   # index(): passa proxima_sessao()/pauta_url() (leitura de cache) ao template
├── tests/
│   ├── fixtures/                # HTML de exemplo das duas páginas do CADE
│   └── test_hub.py
└── ...                          # (apps.py, urls.py, views.py já existentes, sem mudança estrutural)

apps/monitoring/management/commands/run_worker.py   # +1 chamada gated por cadência em _run_cycle
templates/dashboard/index.html                        # +cartão de sessão (condicional)
config/settings.py                                     # +CACHES (backend db), +env HUB_*
config/env_schema.py                                   # cadência mínima configurável
```

**Structure Decision**: Sem app novo — o hub é conteúdo do dashboard já existente, então vive
dentro de `apps/dashboard/` como um módulo (`hub.py`) chamado pela view e pelo passo do worker.
Evita a sobrecarga de um app inteiro para ~150 linhas de busca/parsing (diferente da feature 009,
que tinha modelos e três fluxos próprios justificando um app dedicado).

## Complexity Tracking

*Nenhuma violação da constituição a justificar — todos os gates acima são PASS.*
