# Implementation Plan: Métricas de desenvolvimento assistido por IA

**Branch**: `007-ai-dev-metrics` | **Date**: 2026-09-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-ai-dev-metrics/spec.md`

## Summary

Ferramenta de linha de comando local, só com a biblioteca padrão do Python, que (1) lê as
transcrições do Claude Code, (2) grava os **fatos** de custo num histórico apenas-anexar
encadeado por hash, guardado fora do repositório, (3) calcula no momento do relatório a
atribuição a features, as fases, o first-pass, o retrabalho e a cobertura, (4) escreve um
relatório Markdown por feature em `.ai-metrics/reports/` (ignorado pelo Git) e (5) pede, sob
demanda, uma análise interpretativa a um subprocesso `claude` headless, validada por código.
Um comando `setup`, executado uma única vez, instala o hook em `.claude/settings.local.json`.

A pesquisa (ver [research.md](research.md)) confirmou nos transcritos reais que: a resposta do
assistente repete `usage` idêntico em uma linha por bloco (dedupe por `message.id` é
suficiente); o `turn_duration` do sistema dá o tempo do ciclo; o resultado de `Bash` só
informa falha por `is_error`; e os totais das transcrições ficam **2% a 3,6% abaixo** dos totais
por modelo de `cost-state`, então a validação é uma divergência medida (a spec foi ajustada).
O formato da entrada do hook `Stop` no Windows continua não verificado; o desenho o torna
irrelevante (o hook apenas dispara uma varredura idempotente de todas as transcrições).

## Technical Context

**Language/Version**: Python ≥ 3.11 (desenvolvimento em 3.11.3; produção/CI em 3.12). Só stdlib.

**Primary Dependencies**: nenhuma nova. Usa `argparse`, `json`, `hashlib`, `pathlib`,
`subprocess` (chamadas a `git` e ao `claude`), `fnmatch`, `statistics`, `unittest`. O `claude`
CLI é ferramenta de desenvolvimento já instalada, não dependência Python.

**Storage**: arquivos. Histórico `~/.cade-metrics/wal.jsonl` (+ `head.json`, `errors.log`,
`state.json`, `analysis-cwd/`); relatórios em `.ai-metrics/reports/`. Nenhum banco.

**Testing**: `unittest` (stdlib) em `tools/ai_metrics/tests/`, com transcrições **sintéticas**
como fixtures. Comando: `python -m unittest discover -s tools/ai_metrics/tests -t .`.
`manage.py test tests` (CI atual) não descobre esse diretório.

**Target Platform**: Windows 11 (uso do dono) e Linux/macOS (portátil; sem API específica de SO).

**Project Type**: CLI local de apoio ao desenvolvimento (não faz parte do app Django).

**Performance Goals**: relatório de feature com centenas de turnos em < 10 s (SC-006);
captura pelo hook em < 2 s para uma sessão típica (varredura incremental por tamanho de arquivo).

**Constraints**: nunca gravar texto de prompt/resposta/conteúdo de arquivo/comando; sem valor
monetário; a captura nunca falha o turno (sempre `exit 0` no modo hook); nome do bot nunca
gravado (guarda ativa, ver research R11); leitura e escrita em UTF-8 explícito (Windows).

**Scale/Scope**: dezenas de features, dezenas de milhares de turnos; histórico < 50 MB no
horizonte do estudo. Leitura integral do histórico a cada relatório é aceitável.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação | Resultado |
|-----------|-----------|-----------|
| I. Simplicidade Operacional | Fora do processo Django/Gunicorn/worker; sem daemon, sem fila, sem Redis; zero dependências de runtime; consumo irrelevante para a VM de produção (a ferramenta não vai para a imagem: ver Structure Decision). | ✅ |
| II. Monitoramento Responsável | Não faz requisições ao SEI/CADE. N/A. | ✅ |
| III. Django Monolítico | Não é app de domínio nem serviço: é ferramenta de desenvolvimento em `tools/`, sem lógica no Django e sem novo repositório. | ✅ |
| IV. PostgreSQL em Produção | Nenhum banco novo; o histórico é um arquivo, não um servidor de dados. | ✅ |
| V. Notificações (regra do nome do bot) | O histórico só guarda metadados numéricos, caminhos e identificadores; nunca texto. Guarda extra: recusa gravar qualquer linha que contenha o valor de `TELEGRAM_BOT_USERNAME` (lido do ambiente/`.env`, nunca gravado). | ✅ |
| VI. Humanização | N/A (não notifica usuários). Relatórios em português. | ✅ |
| VII. Portfólio-Ready | Testes automatizados, `--help` descritivo, logs, tratamento explícito de erros (sem silêncio, exceto o modo hook, que registra em `errors.log`). Cobertura de `services/selectors` não se aplica. | ✅ |
| VIII. Sem Over-Engineering | Nenhuma dependência Python nova. Cada mecanismo não trivial tem justificativa em Complexity Tracking. | ✅ com justificativas |
| Workflow 4 (env vars no `.env.example`) | Nenhuma variável de ambiente nova: local do histórico fixo (`~/.cade-metrics`) com `--home` só para testes. | ✅ |
| Tech Stack Canônico | Não altera nenhuma linha da tabela. | ✅ |

**Conclusão**: sem emenda à constituição. Nenhuma violação a justificar além de Complexity Tracking.

**Re-check pós-design (Fase 1)**: mantido. O desenho final não adicionou dependência, banco,
canal, processo ou variável de ambiente. A única exceção nova ao "só leitura" do repositório é a
gravação em `.ai-metrics/`, protegida por FR-040b.

## Project Structure

### Documentation (this feature)

```text
specs/007-ai-dev-metrics/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md
│   ├── wal-events.md
│   ├── analysis-io.md
│   └── config.md
├── checklists/requirements.md
└── tasks.md              # /speckit-tasks (não criado aqui)
```

### Source Code (repository root)

```text
tools/
└── ai_metrics/
    ├── __init__.py
    ├── __main__.py          # python -m tools.ai_metrics
    ├── cli.py               # argparse e despacho dos subcomandos
    ├── setup.py             # setup local único: instala o hook Stop, cria a pasta do histórico
    ├── config.py            # padrões + sobrescrita em ~/.cade-metrics/config.json
    ├── config.default.json
    ├── wal.py               # anexar, ler, verificar, trava, âncora head.json
    ├── ingest.py            # transcrição -> eventos (dedupe, validação vs cost-state, lacunas)
    ├── gitinfo.py           # git via subprocess: branches, reflog, merge, diff
    ├── model.py             # features, aliases, rascunhos, atribuição, situação
    ├── metrics.py           # fases, ciclos, first-pass, correções, churn, contexto, spec, tempo
    ├── report.py            # Markdown por feature, comparação, guarda do .gitignore
    ├── analysis.py          # subprocesso `claude`, validação da saída
    └── tests/
        ├── fixtures/        # transcrições SINTÉTICAS (nunca cópias de conversas reais)
        └── test_*.py

.ai-metrics/                 # dados locais: .gitignore e .dockerignore
└── reports/<featureId>.md
```

**Versionamento (decisão do dono)**: o código em `tools/ai_metrics/` é **versionado normalmente**.
`.gitignore` recebe apenas `.ai-metrics/`. `.dockerignore` recebe `.ai-metrics/` e
`tools/ai_metrics/`, para que nem a ferramenta nem seus dados entrem na imagem.

**Structure Decision**: projeto único em `tools/ai_metrics/`, fora de `apps/`, `config/` e
`tests/` (o CI de produção só roda `manage.py test tests`). `tools/ai_metrics/` e `.ai-metrics/` entram
no `.dockerignore`, então a ferramenta nunca vai para a imagem (o código é versionado; só os
dados locais ficam fora do Git). Nome de pacote sem hífen para poder
ser executado como `python -m tools.ai_metrics` da raiz do repositório.

## Complexity Tracking

| Item | Por que é necessário | Alternativa mais simples rejeitada porque |
|------|----------------------|-------------------------------------------|
| Encadeamento por hash + `head.json` (`hashlib`, ~40 linhas) | FR-005/FR-006 pedem detectar edição **e remoção**; sem âncora, apagar as últimas linhas passa despercebido. | Só `seq` sem hash não detecta edição de valores; só hash sem `head.json` não detecta truncamento no final. |
| Trava por arquivo (`O_EXCL`) | FR-010b: duas sessões podem capturar ao mesmo tempo. | Sem trava, a sequência pode bifurcar. Trava de SO (`msvcrt`/`fcntl`) exigiria código por plataforma. |
| Subprocesso `claude` para a análise | FR-044..049: a interpretação por LLM é requisito da v1. | Chamar API HTTP exigiria chave e SDK/HTTP próprio; o CLI já autenticado é o caminho mais curto. |
| Comando `setup` (10º módulo, `setup.py`) | O dono quer configuração única e automática do hook em vez de editar `settings.local.json` à mão; depois disso o fluxo é só `git switch -c` → trabalhar. | Documentar o trecho JSON exigiria edição manual e é fácil de errar (JSON existente com outras chaves). |
| 10 módulos | Separação natural: fatos (`wal`, `ingest`), derivação (`model`, `metrics`), saída (`report`, `analysis`). | Um arquivo único seria ilegível e mais difícil de testar. |
