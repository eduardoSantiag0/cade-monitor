# Contrato: análise por LLM

## Entrada (montada pelo código, nunca de transcrições)

```json
{
  "promptVersion": "1",
  "feature": {"id": "007-ai-dev-metrics", "workflow": "grill+speckit", "status": "em andamento",
              "dataClass": "observed", "coverage": "complete", "n": 1},
  "metrics": [
    {"id": "M-tokens-total", "value": 123456789, "lowerBound": true, "unit": "tokens"},
    {"id": "M-preimpl-tokens", "value": 4567890, "lowerBound": true, "unit": "tokens"},
    {"id": "M-fix-cycles", "value": 3, "lowerBound": false, "unit": "ciclos"},
    {"id": "M-plan-recall", "value": null, "reason": "não se aplica", "unit": "razão"}
  ],
  "coverage": [{"id": "G-1", "reason": "unlogged-api-calls", "recovered": false}],
  "facts": [{"id": "F-1", "text": "Primeira escrita executável no turno T"}]
}
```

- Só números, rótulos e frases determinísticas geradas por código. Sem texto de conversa, sem
  caminhos de arquivo além dos já presentes nos fatos, sem valores monetários.
- `inputHash` = `sha256` do JSON canônico acima.

## Saída exigida do modelo (JSON puro)

```json
{
  "statements": [
    {"type": "fact",        "text": "...", "evidence": ["M-fix-cycles"], "numbers": [{"metric": "M-fix-cycles", "value": 3}]},
    {"type": "association", "text": "...", "evidence": ["M-preimpl-tokens", "M-fix-cycles"]},
    {"type": "hypothesis",  "text": "...", "evidence": ["M-preimpl-tokens"]},
    {"type": "unsupported", "text": "...", "evidence": []}
  ],
  "limitations": ["..."]
}
```

## Validação (em código; qualquer falha rejeita a análise inteira)

1. JSON válido e no esquema; `type` ∈ {`fact`, `association`, `hypothesis`, `unsupported`}.
2. Toda `evidence` referencia `id` existente em `metrics`/`facts`/`coverage`.
3. `fact`, `association` e `hypothesis` têm ≥ 1 evidência (`unsupported` pode não ter, e é
   exibido como tal, nunca como conclusão).
4. Cada `numbers[].value` é igual ao valor calculado para o `metric`.
5. Linguagem causal proibida (regex sem distinção de maiúsculas): `causou`, `causa`, `reduziu`,
   `reduz`, `porque`, `por causa de`, `devido a`, `levou a`, `resultou em`.
6. Feature parcial (`coverage: partial` ou métrica `lowerBound`): proibido o padrão
   `consumiu ... no total`/`total consumido`.
7. Comparação com features históricas: `limitations` deve mencionar a ausência de custos de
   especificação.
8. `limitations` não vazio.

Rejeitada ⇒ `analysis.generated{accepted:false, rejectReasons}`; o relatório não muda.
Aceita ⇒ seção **Análise** do relatório é (re)escrita a partir do evento mais recente aceito.

## Armazenamento do texto aceito

O evento `analysis.generated` guarda só hashes e o resultado. O **texto** de uma análise aceita fica num
arquivo local `.ai-metrics/analyses/<feature>-<16 primeiros hex do outputHash>.json` (`{"output": {...}}`, ignorado
pelo Git como todo o `.ai-metrics/`). O relatório usa o evento aceito mais recente e só exibe o arquivo se o
`sha256` do conteúdo bater com o `outputHash` do evento; sem o arquivo, a seção **Análise** volta ao texto padrão.
Análises rejeitadas nunca são gravadas em arquivo.

## Execução

`claude -p --output-format json --tools "" --disable-slash-commands` (verificado, ver research R13) com a entrada e o roteiro fixo (versão em `promptVersion`), `cwd` =
`~/.cade-metrics/analysis-cwd/` (vazio, fora do repositório). A transcrição desse subprocesso é
classificada `analysis-overhead` pela origem e nunca atribuída a nenhuma feature.
