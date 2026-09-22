# Phase 0 Research: Hardening e Limpeza Técnica do Repositório

Cada seção resolve uma decisão técnica necessária para implementar um FR de `spec.md`, no formato
Decision / Rationale / Alternatives considered.

## 1. Mecanismo para parar de versionar `data/evolution-postgres/` (FR-001)

- **Decision**: `git rm -r --cached data/evolution-postgres/` (remove do índice, mantém em disco)
  + adicionar `data/evolution-postgres/` ao `.gitignore`. Sem reescrita de histórico (decisão já
  tomada no spec).
- **Achado adicional durante a pesquisa**: o mesmo problema existe, em menor grau, para
  `data/evolution-redis/` (diretório de dados do Redis da Evolution API) e para arquivos `.js`
  soltos em `logs/` (ex.: `logs/abstract.router.js`, `logs/evolution-manager-index.js`,
  `logs/instance.controller.js`, `logs/instance.router.js`) — nenhum dos dois está coberto pelo
  `.gitignore` atual (`logs/*.log` só cobre logs, não `.js`; não há entrada para
  `data/evolution-redis/`). Ambos aparecem como `??` (untracked, não ignorados) no `git status`
  atual, ou seja, um `git add -A` desavisado os versionaria.
- **Rationale**: a intenção do FR-001 (dados de containers auxiliares não pertencem ao histórico
  do git) se aplica igualmente a esses dois casos; corrigir só o Postgres deixaria o mesmo bug
  pronto para acontecer de novo com o Redis. Tratado como parte da mesma tarefa de `.gitignore`,
  não como escopo novo.
- **Alternatives considered**: reescrever histórico agora mesmo (rejeitada — decisão já tomada
  pelo usuário na fase de clarificação do spec); ignorar os arquivos `.js` de `logs/` por
  não fazerem parte do path de execução do Django (rejeitada — ainda são artefatos gerados por
  ferramenta externa que não deveriam estar versionados, mesma lógica do resto do FR).

## 2. Falha rápida para `SECRET_KEY` inseguro em produção (FR-003)

- **Decision**: adicionar um `model_validator` (modo `after`) em `EnvSettings`
  (`config/env_schema.py`) que levanta um erro claro quando `debug is False` e
  (`secret_key` vazio OU igual ao valor padrão de exemplo). Como `EnvSettings.from_env()` já é
  chamado na primeira linha útil de `config/settings.py`, a falha ocorre na subida do processo,
  antes de qualquer request ser aceita.
- **Rationale**: mantém a validação centralizada onde as demais já vivem (Pydantic), reforça o
  padrão "falha rápida" que o próprio docstring de `env_schema.py` já declara como objetivo.
- **Alternatives considered**: Django system check framework (`django.core.checks.register`) —
  rejeitada porque checks (`manage.py check`) não rodam automaticamente antes do Gunicorn/worker
  subir, a menos que explicitamente invocados no processo de deploy; um `raise` no carregamento do
  settings é acionado sempre, sem depender de um passo extra de deploy ser lembrado.

## 3. Estratégia de pin de dependências (FR-006)

- **Decision**: fixar versões exatas diretamente em `requirements.txt` (`Django==5.2.15`,
  `redis==5.x.y`, `pydantic==2.13.5`, etc., usando as versões já validadas no ambiente atual),
  sem introduzir uma ferramenta de lockfile nova (pip-tools/Poetry/PDM).
- **Rationale**: projeto pequeno, poucas dependências diretas — pin manual é suficiente para
  reprodutibilidade e não adiciona uma ferramenta de build nova (Princípio VIII: toda nova
  dependência precisa de justificativa; pip-tools não se justifica para 6 pacotes diretos).
- **Alternatives considered**: `pip-tools` (`pip-compile`) — rejeitada por over-engineering para o
  tamanho atual do projeto; Poetry/PDM — rejeitada por exigir migração de todo o fluxo de
  instalação/Docker, fora do escopo de uma tarefa de hardening.

## 4. Pipeline de CI (FR-007)

- **Decision**: GitHub Actions (`.github/workflows/ci.yml`), gatilho em `push` e `pull_request`
  para a branch principal. Um único job: checkout → setup Python (versão igual à do Dockerfile,
  3.12) → `pip install -r requirements.txt` → `python manage.py test tests`. Variáveis de
  ambiente do job: `SECRET_KEY` com um valor dummy não-padrão (para não disparar a validação do
  FR-003) e `DEBUG=false` (para também exercitar o caminho de produção nos testes). Sem serviço de
  banco externo — os testes usam SQLite em memória/arquivo temporário, como já fazem localmente.
- **Rationale**: o repositório já é hospedado no GitHub (`.github/` já existe na árvore), então
  GitHub Actions não introduz uma conta/serviço novo — apenas ativa um recurso já disponível.
- **Alternatives considered**: GitLab CI / CircleCI / Jenkins — rejeitadas, exigiriam conta e
  integração novas sem nenhum ganho sobre o que já está disponível gratuitamente no GitHub.

## 5. Serviço de rastreamento de erros (FR-010)

- **Decision**: SDK `sentry-sdk` (compatível tanto com Sentry SaaS quanto com uma instância
  self-hosted, caso o dono do projeto prefira depois), inicializado em `config/sentry.py` e
  importado condicionalmente em `settings.py` — só ativa se `SENTRY_DSN` estiver definido no
  ambiente (mesmo padrão de flag opcional já usado para `EVOLUTION_ENABLED`,
  `PROCESS_HASH_REDIS_ENABLED`). Captura exceções não tratadas no loop do `run_worker` e no laço
  do `scheduler` do `docker-compose.yml`.
- **Rationale**: resolve o FR-010 desta spec e também é reaproveitado como o canal de alerta que a
  spec 004 (confiabilidade operacional) vai precisar — investir nele uma vez só.
- **Alternatives considered**: só melhorar o log estruturado local — rejeitada, não resolve o
  problema real (ninguém lê o log até um assinante reclamar); stack própria de observabilidade
  (Prometheus/Grafana/Alertmanager) — rejeitada por violar os Princípios I e VIII para o porte
  atual do projeto.

## 6. Parar de baixar o anexo inteiro para o canal WhatsApp (FR-009)

- **Decision**: em `apps/notifications/services.py::_prepare_attachments_for_channel`, tornar o
  caminho de preparo de anexo ciente do canal: para `NotificationChannel.WHATSAPP`, **não chamar**
  `download_document()` (que baixa o corpo inteiro) — a Evolution API já recebe apenas a URL
  pública do documento, então o conteúdo baixado nunca era usado para esse canal. Continuar
  chamando `download_document()` normalmente apenas para `NotificationChannel.EMAIL`, que
  realmente precisa dos bytes para anexar ao e-mail.
- **Rationale**: a causa raiz não é "falta uma forma mais barata de checar o tamanho" — é que o
  download nunca deveria ter acontecido para esse canal, já que o resultado é descartado. Remover
  a chamada é mais simples e mais correto do que otimizar um download que não deveria existir.
- **Alternatives considered**: usar um `HEAD` request para obter `Content-Length` antes de decidir
  — rejeitada como solução principal porque ainda seria trabalho desnecessário (o WhatsApp/canal
  nunca usa o conteúdo); pode ser reavaliada no futuro apenas se a Evolution API vier a exigir uma
  pré-validação de tamanho do lado do CADE Monitor, o que não é o caso hoje.

## 7. Verificação de remoção completa do código legado (FR-004)

- **Decision**: além de excluir `cademon/`, `wa-bot/`, `tests/test_scraper.py` e os scripts
  associados (`scripts/rebuild_venv.sh`, `scripts/install_whatsapp_bot.sh`,
  `scripts/keepalive_whatsapp.sh` — revisar cada um antes de apagar, pois `rebuild_venv.sh` pode
  conter lógica genérica reaproveitável além da referência a `cademon`), a tarefa de verificação
  roda `grep -rn "cademon\|wa-bot" --include="*.py" --include="*.md" --include="*.sh"` sobre o
  repositório (fora de `.git/`) como critério de aceite manual antes de considerar o FR concluído.
- **Rationale**: garante que a remoção não deixa referências mortas (imports quebrados,
  documentação apontando para caminho inexistente).
- **Alternatives considered**: script de CI dedicado para essa checagem — considerado
  desnecessário para uma verificação pontual de remoção (não é uma regra permanente do projeto).

## 8. Cobertura de teste para o fallback do cache Redis (FR-011 / emenda da constituição)

- **Decision**: adicionar um teste em `tests/test_monitoring.py` que roda `run_check` com
  `PROCESS_HASH_REDIS_ENABLED=False` (via `override_settings`) e confirma que a detecção de
  mudança/sem-mudança continua correta usando somente `MonitoredProcess.last_hash`. Isso prova em
  teste automatizado a cláusula MUST que a emenda da constituição (v1.1.0) exige ("a aplicação
  MUST permanecer funcional com esse cache desabilitado").
- **Rationale**: a emenda da constituição criou uma obrigação nova; sem um teste, nada garante que
  uma mudança futura em `cache.py` quebre esse fallback silenciosamente.
- **Alternatives considered**: nenhuma — item de baixo custo e alto valor, sem trade-off real.

## 9. Conteúdo do README restaurado (FR-002)

- **Decision**: recuperar o README do commit `97936b5` (`git show 97936b5:README.md`, 302 linhas)
  como ponto de partida, em vez de escrever um novo do zero. Conteúdo inspecionado: já descreve
  stack, quick start e propósito do projeto de forma consistente com o que existe hoje (bate com a
  tabela de Tech Stack Canônico da constituição). Ajustes necessários antes de restaurar: (a)
  adicionar menção ao fluxo de `.specify/`/Spec Kit usado no projeto, (b) revisar se os comandos de
  quick start ainda batem com `.env.example` atual, (c) adicionar nota/badge de CI assim que o
  FR-007 for concluído.
- **Rationale**: reduz risco de perder contexto/decisões já documentadas; restaurar cegamente sem
  revisão (rejeitado no spec) e reescrever do zero (mais caro, descarta trabalho válido) eram os
  dois extremos — esta é a opção intermediária já prevista nas Assumptions do spec.
- **Alternatives considered**: README novo do zero — rejeitado, descartaria conteúdo ainda válido;
  restauração sem revisão — rejeitado explicitamente pelas Assumptions do spec.md.

## Resumo de dependências novas introduzidas por esta feature

| Dependência | Tipo | Justificativa (Princípio VIII) |
|---|---|---|
| `sentry-sdk` | Runtime (Python) | FR-010; ver Complexity Tracking em `plan.md` |
| GitHub Actions (`.github/workflows/ci.yml`) | Infraestrutura de CI, não-Python | FR-007; ver Complexity Tracking em `plan.md` |

Nenhuma outra dependência nova é introduzida — `pip-tools`, SDKs de mensageria alternativos e
ferramentas de observabilidade mais pesadas foram avaliados e rejeitados acima.
