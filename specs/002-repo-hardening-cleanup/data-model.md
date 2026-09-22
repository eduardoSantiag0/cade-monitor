# Phase 1 Data Model: Hardening e Limpeza Técnica do Repositório

## Resumo

Esta feature **não introduz nenhuma nova entidade de domínio** e **não requer nenhuma migration**
de banco de dados. É hardening/qualidade sobre modelos e fluxos já existentes. As seções abaixo
documentam, por transparência, os pontos de configuração/validação tocados — que não são
entidades de dados, mas fazem parte do "modelo" de comportamento validado por esta spec.

## Regras de validação adicionadas (não são entidades, mas são contratos verificáveis)

### `EnvSettings` (`config/env_schema.py`) — FR-003

- **Regra nova**: se `debug is False` e (`secret_key` vazio OU `secret_key` igual ao valor padrão
  `'django-insecure-troque-antes-de-colocar-em-producao'`), a construção de `EnvSettings` MUST
  levantar um erro de validação explícito.
- **Não muda**: nenhum campo existente de `EnvSettings` é removido ou renomeado; a mudança é
  puramente uma regra de validação adicional (`model_validator`).

## Entidades existentes referenciadas (sem alteração de esquema)

- **`MonitoredProcess.last_hash`** (`apps/processes/models.py`): usado como fonte de verdade do
  fallback quando o cache Redis está desabilitado (FR-011). Nenhum campo novo — apenas um teste
  automatizado novo (ver `research.md`, item 8) passa a cobrir esse caminho explicitamente.
- **`DetectedDocument`** (`apps/monitoring/models.py`): consumido por
  `_prepare_attachments_for_channel` (FR-009). Nenhum campo novo — a mudança é de comportamento
  (não baixar o binário para o canal WhatsApp), não de esquema.

## Configuração de repositório tocada (não é dado de aplicação, mas é "estado" versionado)

| Arquivo | Mudança | FR relacionado |
|---|---|---|
| `.gitignore` | Adiciona `data/evolution-postgres/`, `data/evolution-redis/`, e um padrão para os `.js` soltos em `logs/` | FR-001 |
| `requirements.txt` | Todas as versões passam de range (`>=`) para pin exato (`==`) | FR-006 |
| `Makefile` | Remove bloco de targets duplicado | FR-005 |
| `.github/workflows/ci.yml` (novo) | Pipeline de CI | FR-007 |
| `config/sentry.py` (novo) | Inicialização opcional do SDK de erro, ativada por `SENTRY_DSN` | FR-010 |
| `README.md` | Restaurado a partir do commit `97936b5`, revisado | FR-002 |

## Itens explicitamente fora do escopo de dados desta feature

- Nenhuma migration Django é criada ou esperada.
- Nenhum campo de nenhum model existente é removido, renomeado ou tem seu tipo alterado.
- A remoção de `cademon/`/`wa-bot/` (FR-004) não toca em nenhum dado persistido — são módulos de
  código sem models Django próprios.
