# Tasks: Hardening e Limpeza Técnica do Repositório

**Input**: Design documents from `/specs/002-repo-hardening-cleanup/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅ (sem `contracts/` — feature não expõe interface externa nova)

**Tests**: Incluídos. A constituição do projeto (v1.1.0, Development Workflow item 2) exige "ao menos um teste unitário cobrindo o caminho feliz e um caso de erro" para novos services — tratado aqui como requisito do projeto, não como opção.

**Organization**: Tarefas agrupadas pelas 4 user stories de `spec.md` (US1–US4), cada uma independentemente entregável. FR-010 e FR-011 não pertencem a nenhuma user story específica (são conformidade/observabilidade cross-cutting) e ficam na fase de Polish.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: US1–US4, mapeando para `spec.md`
- Caminhos de arquivo exatos em cada descrição

---

## Phase 1: Setup

**Purpose**: Estabelecer uma linha de base segura antes de qualquer mudança — este é um repositório existente em produção, não um projeto novo.

- [X] T001 Confirmar working tree limpo (`git status`) e nenhuma mudança não commitada perdida antes de iniciar
- [X] T002 Rodar `make test` e registrar o resultado atual como baseline de regressão (deve passar antes de qualquer task abaixo começar a alterar código)

---

## Phase 2: Foundational

**Purpose**: Nenhuma tarefa bloqueante identificada. As quatro user stories tocam partes independentes do repositório (dados versionados no git, código legado, CI/dependências, views de notificação manual) e não compartilham pré-requisito técnico comum além do Setup acima — podem ser implementadas em qualquer ordem ou em paralelo.

**Checkpoint**: Nenhum — avançar direto para as user stories.

---

## Phase 3: User Story 1 - Repositório seguro e íntegro para qualquer colaborador (Priority: P1) 🎯 MVP

**Goal**: Clonar o repositório do zero não deve trazer dados binários de banco, a aplicação não deve subir em produção com segredo inseguro, e o README deve explicar o projeto.

**Independent Test**: Ver `quickstart.md` seções FR-001, FR-002, FR-003.

### Implementation for User Story 1

- [X] T003 [P] [US1] Remover `data/evolution-postgres/` do índice do git: `git rm -r --cached data/evolution-postgres/`
- [X] T004 [P] [US1] Remover `data/evolution-redis/` do índice do git: `git rm -r --cached data/evolution-redis/` (achado do `research.md` item 1 — mesma causa raiz do FR-001)
- [X] T005 [US1] Atualizar `.gitignore` adicionando `data/evolution-postgres/`, `data/evolution-redis/` e um padrão para os `.js` soltos em `logs/` (ex.: `logs/*.js`), cobrindo `logs/abstract.router.js`, `logs/evolution-manager-index.js`, `logs/instance.controller.js`, `logs/instance.router.js`
- [X] T006 [P] [US1] Recuperar o conteúdo anterior do README: `git show 97936b5:README.md > README.md`
- [X] T007 [US1] Revisar e atualizar `README.md` (depende de T006): conferir se os comandos de "início rápido" batem com `.env.example` e `docker-compose.yml` atuais, adicionar menção ao fluxo `.specify/`/Spec Kit usado no projeto
- [X] T008 [P] [US1] Adicionar `model_validator` em `config/env_schema.py::EnvSettings` que levanta erro explícito quando `debug is False` e `secret_key` está vazio ou igual ao valor padrão de exemplo
- [X] T009 [P] [US1] Adicionar teste unitário em `tests/test_env_schema.py` (novo arquivo) cobrindo: (a) `debug=False` + `secret_key` vazio → erro; (b) `debug=False` + valor padrão de exemplo → erro; (c) `debug=False` + chave válida → sucesso; (d) `debug=True` + `secret_key` vazio → sucesso (caminho de desenvolvimento não é afetado)
- [X] T010 [US1] Validar manualmente os 3 cenários de `quickstart.md` (seção FR-003) rodando `python manage.py check` com cada combinação de `DEBUG`/`SECRET_KEY`

**Checkpoint**: US1 completa e testável de forma independente — repositório limpo, README presente, SECRET_KEY validado.

---

## Phase 4: User Story 2 - Uma única fonte de verdade para o código de scraping e notificação (Priority: P1)

**Goal**: Remover `cademon/` e `wa-bot/` sem deixar referências soltas nem quebrar a suíte de testes.

**Independent Test**: Ver `quickstart.md` seção FR-004.

### Implementation for User Story 2

- [X] T011 [P] [US2] Remover o diretório `cademon/` inteiro: `git rm -r cademon/`
- [X] T012 [P] [US2] Remover o diretório `wa-bot/` inteiro: `git rm -r wa-bot/`
- [X] T013 [P] [US2] Remover `tests/test_scraper.py` (só testa `cademon/scraper.py`, que deixa de existir): `git rm tests/test_scraper.py`
- [X] T014 [US2] Revisar individualmente `scripts/rebuild_venv.sh`, `scripts/install_whatsapp_bot.sh`, `scripts/keepalive_whatsapp.sh`: remover os que só fazem sentido para `cademon`/`wa-bot`; se `rebuild_venv.sh` tiver lógica genérica reaproveitável (não específica de `cademon`), mantê-lo e apenas remover trechos específicos
- [X] T015 [US2] Rodar `grep -rn "cademon\|wa-bot" --include="*.py" --include="*.md" --include="*.sh" . --exclude-dir=.git --exclude-dir=specs` e confirmar nenhuma ocorrência solta fora de `specs/` (onde esta decisão fica documentada)
- [X] T016 [US2] Rodar `make test` e confirmar que a suíte passa sem depender de `tests/test_scraper.py`

**Checkpoint**: US2 completa — código legado removido, suíte de testes intacta, sem referências mortas.

---

## Phase 5: User Story 3 - Build reprodutível e verificado automaticamente (Priority: P2)

**Goal**: Duas instalações de `requirements.txt` resultam nas mesmas versões, e todo push/PR roda a suíte de testes automaticamente.

**Independent Test**: Ver `quickstart.md` seções FR-006, FR-007.

### Implementation for User Story 3

- [X] T017 [US3] Fixar versões exatas em `requirements.txt`: `Django==5.2.15`, `pydantic==2.13.5`, `python-dotenv==1.2.2`, `whitenoise==6.12.0` (versões já validadas no ambiente atual) e `redis`/`gunicorn` na versão estável mais recente disponível no momento da execução desta tarefa (registrar a versão exata escolhida no commit, já que nenhuma das duas está instalada no `.venv` local hoje para confirmar uma versão já validada)
- [X] T018 [US3] Validar manualmente SC-005: instalar `requirements.txt` em dois ambientes limpos (ex.: dois containers Docker descartáveis) e confirmar `pip freeze` idêntico nos dois (depende de T017 — valida o resultado do pin, não pode rodar antes dele)
- [X] T019 [US3] Criar `.github/workflows/ci.yml`: gatilho em `push` e `pull_request` para a branch principal; job único (checkout → setup Python 3.12 → `pip install -r requirements.txt` → `python manage.py test tests`); variáveis de ambiente do job: `SECRET_KEY` com valor dummy não-padrão e `DEBUG=false` (para não disparar a validação de T008 e também exercitá-la como smoke test)
- [ ] T020 [US3] Validar manualmente FR-007: abrir um Pull Request de teste com uma alteração que quebra deliberadamente um teste existente, confirmar que o check do GitHub Actions falha visivelmente no PR, depois reverter a alteração de teste

**Checkpoint**: US3 completa — dependências fixadas, CI rodando a suíte automaticamente em cada PR.

---

## Phase 6: User Story 4 - Envio manual de notificações consistente e eficiente (Priority: P3)

**Goal**: Uma única implementação compartilhada para as 4 views de envio manual; canal WhatsApp para de baixar o anexo inteiro sem necessidade.

**Independent Test**: Ver `quickstart.md` seções FR-008, FR-009.

### Tests for User Story 4 ⚠️

> Escrever estes testes primeiro e confirmar que falham antes de implementar

- [X] T021 [P] [US4] Adicionar teste em `tests/test_notifications.py` que mocka `download_document` e confirma: NÃO é chamado quando `notification.channel == NotificationChannel.WHATSAPP`; é chamado normalmente quando `notification.channel == NotificationChannel.EMAIL`

### Implementation for User Story 4

- [X] T022 [US4] Criar uma função de serviço compartilhada (ex.: `apps/processes/services.py::dispatch_manual_notifications_for_process`) que recebe processo + config (assunto, corpo de e-mail, corpo de WhatsApp, exigir anexo ou não) e itera assinaturas, contando envios/falhas por canal — extraindo o padrão hoje repetido nas 4 views
- [X] T023 [US4] Refatorar `process_send_test_email` em `apps/processes/views.py` para usar o helper de T022 (depende de T022)
- [X] T024 [US4] Refatorar `process_notify_subscribers` em `apps/processes/views.py` para usar o helper de T022 (depende de T022)
- [X] T025 [US4] Refatorar `process_send_test_whatsapp` em `apps/processes/views.py` para usar o helper de T022 (depende de T022)
- [X] T026 [US4] Refatorar `process_send_latest_update` em `apps/processes/views.py` para usar o helper de T022, preservando sua lógica extra de anexo/protocolo (a view mais complexa das quatro — pode exigir um parâmetro/hook adicional no helper) (depende de T022)
- [X] T027 [US4] Em `apps/notifications/services.py::_prepare_attachments_for_channel`, parar de chamar `download_document` quando `notification.channel == NotificationChannel.WHATSAPP` (o conteúdo baixado nunca é usado para esse canal — apenas a URL é enviada à Evolution API); manter a chamada para `NotificationChannel.EMAIL` (depende de T021 — teste já escrito e falhando)
- [X] T028 [US4] Medir e confirmar SC-006 (redução ≥60% nas linhas hoje duplicadas entre as 4 views) comparando `wc -l apps/processes/views.py` antes/depois

**Checkpoint**: US4 completa — views consolidadas, download desnecessário eliminado, coberto por teste.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: FR-005 (Makefile), FR-010 (rastreamento de erros) e FR-011 (conformidade do fallback Redis) não pertencem a nenhuma user story específica — são conformidade/qualidade cross-cutting desta feature.

- [X] T029 [P] Remover o bloco de targets duplicado em `Makefile`, mantendo cada target (`install`, `migrate`, `superuser`, `run`, `worker`, `test`, `check`, `collectstatic`, `clean`, `digest`, `backup`) definido exatamente uma vez
- [X] T030 [P] Criar `config/sentry.py` com inicialização condicional do SDK de erro (`sentry_sdk.init(...)`), ativada apenas quando a variável de ambiente `SENTRY_DSN` estiver definida, seguindo o padrão de flag opcional já usado no projeto (`EVOLUTION_ENABLED`, `PROCESS_HASH_REDIS_ENABLED`)
- [X] T031 Importar e inicializar `config/sentry.py` em `config/settings.py`, antes de qualquer outro código que possa lançar exceção (depende de T030)
- [X] T032 Instrumentar `apps/monitoring/management/commands/run_worker.py` para capturar exceção não tratada no loop principal e reportá-la via `sentry_sdk.capture_exception` antes/além do log local existente (depende de T031)
- [X] T033 Adicionar `sentry-sdk` a `requirements.txt` com versão exata fixada (depende de T017 — mesmo arquivo; fazer depois para não gerar conflito de merge)
- [X] T034 [P] Adicionar teste em `tests/test_monitoring.py` que roda `run_check` com `PROCESS_HASH_REDIS_ENABLED=False` (via `override_settings`) e confirma detecção correta de mudança/sem-mudança usando somente `MonitoredProcess.last_hash` — prova a cláusula MUST da emenda da constituição v1.1.0 (FR-011)
- [X] T035 Rodar `make test` completo (regressão final de todas as user stories, incluindo os testes novos de T009, T021, T034)
- [X] T036 Executar cada comando de `quickstart.md` manualmente, na ordem, e confirmar todos os resultados esperados antes de considerar a feature concluída

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências — pode começar imediatamente
- **Foundational (Phase 2)**: vazia nesta feature — não bloqueia nada
- **User Stories (Phase 3–6)**: cada uma depende apenas do Setup (T001–T002); são independentes entre si e podem ser feitas em qualquer ordem ou em paralelo
- **Polish (Phase 7)**: T029/T030/T034 podem começar a qualquer momento após o Setup; T031/T032 dependem de T030; T033 depende de T017 (US3, mesmo arquivo `requirements.txt`); T035/T036 dependem de todas as fases anteriores estarem concluídas

### User Story Dependencies

- **US1 (P1)**: sem dependência de outras stories
- **US2 (P1)**: sem dependência de outras stories
- **US3 (P2)**: sem dependência de outras stories (T017 coordena com T033 apenas por tocarem o mesmo arquivo `requirements.txt`, não por ordem lógica obrigatória)
- **US4 (P3)**: sem dependência de outras stories

### Parallel Opportunities

- T003, T004, T006, T008 podem rodar em paralelo (arquivos/diretórios diferentes) logo após o Setup
- T011, T012, T013 podem rodar em paralelo (diretórios/arquivos diferentes)
- T018 depende de T017 (valida o resultado do pin) — não é paralelo a ele
- T021 (teste) deve ser escrito e confirmado falhando antes de T027 (implementação) — não são paralelos entre si, mas T021 pode rodar em paralelo a T022–T026 (arquivo diferente)
- T029, T030, T034 podem rodar em paralelo entre si e em paralelo às fases de US1–US4; T033 depende de T017 (mesmo arquivo `requirements.txt`)

---

## Parallel Example: User Story 1

```bash
# Após o Setup (T001-T002), lançar em paralelo:
Task: "Remover data/evolution-postgres/ do índice do git"
Task: "Remover data/evolution-redis/ do índice do git"
Task: "Recuperar conteúdo anterior do README de 97936b5"
Task: "Adicionar validação de SECRET_KEY inseguro em config/env_schema.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup (T001–T002)
2. Completar Phase 3: User Story 1 (T003–T010)
3. **PARAR e VALIDAR**: rodar as validações de `quickstart.md` FR-001/FR-002/FR-003
4. Este já é um incremento de valor real — pode ser commitado/mergeado isoladamente

### Incremental Delivery

1. Setup → US1 (repositório seguro) → commit/PR
2. US2 (código legado removido) → commit/PR
3. US3 (build reprodutível + CI) → commit/PR — a partir daqui, os PRs seguintes já são protegidos por CI
4. US4 (views consolidadas + fix do anexo WhatsApp) → commit/PR
5. Polish (Makefile, Sentry, teste do fallback Redis) → commit/PR final desta feature

### Notes

- Cada user story é seu próprio PR recomendado — evita um PR gigante difícil de revisar e permite mergear valor incrementalmente (alinhado ao FR-007 assim que ele existir).
- T017 e T033 tocam o mesmo arquivo (`requirements.txt`); fazer T017 antes de T033 evita reescrever o arquivo duas vezes.
- Rodar `make test` (T002) antes de começar e (T035) ao final garante que nenhuma regressão passou despercebida.
