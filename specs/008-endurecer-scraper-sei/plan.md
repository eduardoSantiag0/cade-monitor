# Implementation Plan: Endurecimento da resolução de processo no SEI/CADE

**Branch**: `008-endurecer-scraper-sei` | **Date**: 2026-09-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-endurecer-scraper-sei/spec.md`

## Summary

Hoje `apps/monitoring/clients.py` resolve um número de processo para a URL pública de detalhe do
SEI com uma única tentativa de POST, usando um payload de campos ocultos fixado no código e
buscando somente pelo campo de protocolo. Isso falha silenciosamente quando (a) só a busca por
texto livre ou por número de documento encontraria o processo, (b) o SEI muda um campo oculto do
formulário, ou (c) o usuário digita o número com um zero a mais no início. A abordagem técnica é
ler os defaults do formulário via uma requisição GET antes de montar o
POST, tentar em sequência três estratégias de busca (protocolo → texto → nº de documento) parando
na primeira que resolver, normalizar o número do processo antes de pesquisar, e escolher o link de
detalhe pelo trecho da página que realmente cita o processo pesquisado (em vez do primeiro link da
página). Tudo dentro do módulo `monitoring` já existente, sem nova dependência e sem mudar a
interface pública consumida pelo bot do Telegram e por `apps/processes/services.py`.

## Technical Context

**Language/Version**: Python 3.11 (Django 5.2.15)

**Primary Dependencies**: Django 5.2, Pydantic 2.x (`Snapshot`/`AttachmentPayload`), `urllib`
da stdlib (já em uso) — nenhuma dependência nova.

**Storage**: N/A — sem mudança de modelos/migrations; reaproveita `MonitoredProcess` já existente.

**Testing**: `django.test.TestCase` (unittest), com fixtures HTML locais e `unittest.mock.patch`
para as chamadas HTTP (Princípio "Scrapers/extractors MUST ser testados com fixtures HTML locais").

**Target Platform**: Linux (Docker/Render), processo Django único (Gunicorn 1 worker/2 threads).

**Project Type**: Web service (monolito Django) — mudança inteira contida no app `monitoring`.

**Performance Goals**: Mesmo orçamento de tempo já usado hoje para resolver um processo; a
resolução pode passar de 1 requisição para até 4 (1 GET de defaults + até 3 POSTs em sequência),
mas isso acontece uma vez por ciclo de verificação (≥ 25 min/processo), não aumenta a frequência
de scraping por processo.

**Constraints**: Sem nova dependência de runtime; sem requisições paralelas (sequencial, como
hoje); deve caber na política de retry/backoff já configurada (`REQUEST_RETRY_ATTEMPTS`,
`REQUEST_RETRY_BACKOFF_SECONDS`); deve rodar dentro do limite de 1–2 vCPU / ≤ 512 MB (Princípio I).

**Scale/Scope**: Mesma escala atual (dezenas de processos monitorados); mudança é local à
resolução de um único processo por vez.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
|---|---|
| I. Simplicidade Operacional | **PASS** — continua usando só `urllib` da stdlib; não introduz serviço, fila ou processo novo. O fallback via navegador (Playwright) foi deliberadamente deixado fora de escopo (ver spec.md, Assumptions) por exigir uma dependência de runtime nova. |
| II. Monitoramento Responsável | **PASS** — continua HTTP não autenticado a endpoints públicos, sequencial (sem burst/paralelismo). A busca por formulário já usa POST desde a feature 001 (comportamento pré-existente, não introduzido aqui); a mudança amplia de 1 para até 4 requisições *dentro de um mesmo ciclo* de resolução, sem alterar a cadência mínima entre ciclos (≥ 25 min/processo). |
| III. Django Monolítico Bem Organizado | **PASS** — mudança inteira dentro do app `monitoring` já existente (`clients.py`, `extractors.py`); nenhuma lógica de negócio nova em views/models. |
| IV. PostgreSQL em Produção | **N/A** — sem mudança de schema ou migration. |
| V. Notificações | **N/A** — não altera canais de notificação. |
| VI. Humanização das Mensagens | **N/A** — não altera formato de diff/mensagem ao usuário. |
| VII. Portfólio-Ready — Qualidade de Código | **PASS** — exige novos testes com fixtures HTML locais para os três payloads de busca e para a leitura de defaults do formulário; sem chamada HTTP real em teste. |
| VIII. Sem Over-Engineering | **PASS** — zero dependências novas; navegador headless (Playwright) explicitamente descartado nesta feature por falta de justificativa suficiente agora (ver Complexity Tracking). |

Nenhuma violação sem justificativa — ver Complexity Tracking abaixo apenas para registrar a
decisão já tomada no spec de **não** portar o fallback de navegador.

## Project Structure

### Documentation (this feature)

```text
specs/008-endurecer-scraper-sei/
├── plan.md              # Este arquivo
├── research.md          # Fase 0
├── data-model.md         # Fase 1 (sem novas entidades — ver conteúdo)
├── quickstart.md         # Fase 1
├── contracts/
│   └── process-resolution.md
└── tasks.md              # Fase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
apps/monitoring/
├── clients.py        # _fetch_by_process_number ganha as 3 estratégias + leitura de defaults
│                      # do formulário; resolve_process_url/lookup_process_url/get_snapshot
│                      # mantêm a mesma assinatura
├── extractors.py      # nova InputDefaultsParser + extract_input_defaults();
│                      # extract_process_detail_url() ganha parâmetro opcional process_number;
│                      # nova normalize_cade_process_number()
tests/
└── test_monitoring.py  # novos casos: 3 estratégias, defaults dinâmicos, zero a mais,
                         # múltiplos processos na mesma página de resultado
```

**Structure Decision**: mudança cirúrgica dentro do app `monitoring` já existente (Princípio III
— nenhum app novo, nenhuma pasta nova). `extract_process_detail_url` ganha um parâmetro opcional
para não quebrar nenhum outro chamador que hoje o use sem número de processo.

## Complexity Tracking

> Sem violações da constituição a justificar. A única complexidade deliberadamente **não**
> adicionada foi o fallback via navegador headless (Playwright):

| Violação (não aplicada) | Quando seria necessária | Por que não adicionar agora |
|---|---|---|
| Navegador headless (Playwright) para páginas dependentes de JS | Algumas páginas do SEI só renderizam certos dados via JavaScript | Introduziria dependência de runtime nova e maior consumo de memória, contrariando o Princípio I (VM de 1–2 vCPU / ≤ 512 MB); as 3 estratégias de busca via HTTP simples já resolvem o problema relatado (busca falhando silenciosamente); pode virar feature própria se surgir um caso real que exija JS |
