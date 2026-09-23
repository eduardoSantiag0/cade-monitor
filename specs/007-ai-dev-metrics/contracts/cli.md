# Contrato: linha de comando

Execução da raiz do repositório: `python -m tools.ai_metrics <comando> [opções]`.
Opção global `--home <dir>` (padrão `~/.cade-metrics`) existe para testes. Todo comando tem
`--help` descritivo em português. Saída em UTF-8. Códigos de saída: `0` ok, `1` erro de uso ou
dados, `2` integridade comprometida (`verify` e comandos que recusam trabalhar sobre dados suspeitos).

## Setup (uma única vez)

| Comando | Faz | Notas |
|---------|-----|-------|
| `setup [--dry-run] [--remove] [--check]` | Prepara a máquina para o tracking automático | Ver regras abaixo |

`setup` (idempotente; rodar de novo não duplica nada):

1. Cria `~/.cade-metrics/` (histórico ainda vazio, sem `head.json`).
2. **Instala o hook `Stop`** em `.claude/settings.local.json` da raiz do repositório: cria o
   arquivo se faltar; se existir, faz cópia `.bak`, **mescla** só a entrada `hooks.Stop` e
   preserva todas as outras chaves (inclusive outros hooks `Stop`); reconhece a entrada própria
   pelo comando e a atualiza em vez de duplicar. JSON existente inválido → aborta sem alterar nada.
3. O comando gravado usa o caminho absoluto do Python que rodou o `setup` e do `__main__.py`
   da ferramenta, com `ingest --hook` (não depende do diretório de trabalho do hook).
4. Confere que `.ai-metrics/` está ignorado pelo Git (`git check-ignore`) e avisa se não estiver.
5. Faz uma primeira captura (`ingest`) e imprime o resumo. Não roda `backfill` (é decisão explícita).

`--dry-run` mostra o que mudaria sem gravar; `--check` só informa se o hook está instalado e se a
pasta do histórico existe (`exit 1` se faltar); `--remove` tira apenas a entrada da ferramenta
do `settings.local.json` (mantém o histórico). Depois do `setup`, o fluxo é
`git switch -c <feature>` → trabalhar → captura automática.

## Captura

| Comando | Faz | Notas |
|---------|-----|-------|
| `ingest [--hook] [--final] [--quiet]` | Varre transcrições do projeto (e do `analysis-cwd`), grava eventos novos, valida contra `session.cost`, registra lacunas | `--hook`: **sempre `exit 0`**, sem saída, erros vão para `~/.cade-metrics/errors.log` (uma linha `timestamp<TAB>NÍVEL<TAB>contexto<TAB>mensagem`; só linhas `ERROR` viram lacuna `hook-failed`), ignora o stdin. `--final`: aceita a última resposta mesmo incompleta. Sem opções: resumo (novos turnos, divergência por sessão) |
| `verify` | Confere sequência, encadeamento e `head.json` | Imprime a primeira `seq` comprometida; `exit 2` se falhar. Antes de conferir, descarta uma última linha **incompleta sem quebra de linha** que a âncora ainda não reconhece (queda no meio da gravação) e conserta a âncora se estiver uma posição atrás; edição ou remoção de registros reconhecidos continua sendo falha |

## Relatórios

| Comando | Faz | Notas |
|---------|-----|-------|
| `report <featureId\|alias> [--stdout] [--no-write]` | Gera o Markdown da feature | Grava em `.ai-metrics/reports/<featureId>.md` (sobrescreve) e/ou imprime. Inclui a **análise aceita mais recente**, se houver. **Recusa gravar** se `.ai-metrics/` não estiver ignorado pelo Git (`git check-ignore`). Roda `verify` antes: se falhar, avisa e `exit 2` |
| `report --all` | Um relatório por feature conhecida + `_comparacao.md` | |
| `compare [--stdout]` | Comparação entre workflows (só elegíveis) com `n`, classes de custo, vieses, `unattributed` por workflow | Grava `.ai-metrics/reports/_comparacao.md` |
| `timeline` | Lista features em ordem cronológica com situação, `dataClass`, `coverage`, workflow e, à parte, o custo fora de features (exploração sem entrega, `unattributed`, sobrecarga de análise) | |

## Correções e declarações (geram eventos)

| Comando | Evento |
|---------|--------|
| `feature use <id\|none> [--workflow w] [--tag t] [--reason r] (--session s \| --from ts --to ts \| --turns ids)` | `attribution.set` (o "`/feature`" da spec). Exige um escopo; `none` declara o período como `unattributed`; se o id for **desconhecido**, grava antes um `feature.born` declarado (`observed`/`complete`) |
| `feature correct <seq> --feature <id\|none> [...mesmas opções]` | `attribution.corrected` (reaproveita o escopo do registro corrigido se nenhum for informado) |
| `feature status <id> <em-andamento\|entregue\|abandonada> [--reason ..]` | `status.corrected` |
| `feature first-pass <id> <cycleUuid\|unknown>` | `firstPass.corrected` |
| `feature tag <id> --session s --tag setup` | `attribution.set` com `tag` |
| `gap add --source s --from ts --to ts --reason r [--feature id]` | `coverage.gap` (`r` ∈ `copilot`, `hook-failed`, `transcript-missing`, `unlogged-api-calls`, `unreadable-lines`) |
| `backfill` | `feature.born` (`historical`/`partial`, com a janela dos commits de `history_windows`), `feature.alias` (`path-evidence`) e `coverage.gap` (`copilot`); a atribuição dos turnos é derivada no relatório, dentro da janela; idempotente |

## Análise

| Comando | Faz |
|---------|-----|
| `analyze <featureId> [--model m]` | Monta a entrada estruturada, roda `claude -p` em `analysis-cwd`, valida, grava `analysis.generated` e, se aceita, anexa a seção **Análise** ao relatório. Rejeitada: não altera o relatório e lista os motivos |

## Regras transversais

- Nenhum comando imprime ou grava o valor de `TELEGRAM_BOT_USERNAME`.
- Comandos de leitura (`report`, `compare`, `timeline`, `analyze`) nunca acrescentam registros ao histórico,
  exceto `analyze` (`analysis.generated`); todos rodam `verify` antes e recusam dados suspeitos (`exit 2`).
- Opções ocultas, só para testes e diagnóstico: `--repo`, `--projects-dir` e `ingest --dump-stdin <arquivo>`
  (registra uma vez o stdin e o cwd do hook; o stdin traz o texto da resposta, então apague o arquivo depois).
- Mensagens de erro em português e com o próximo passo sugerido.
