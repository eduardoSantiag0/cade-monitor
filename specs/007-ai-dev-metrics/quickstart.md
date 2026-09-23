# Quickstart: validar a ferramenta de métricas

Roteiro de validação ponta a ponta. Detalhes de formatos: [contracts/](contracts/) e
[data-model.md](data-model.md). Todos os comandos rodam da raiz do repositório.

## Pré-requisitos

- Python ≥ 3.11 e Git; o `claude` CLI autenticado (só para a etapa 7).
- `.gitignore` com `.ai-metrics/`; `.dockerignore` com `.ai-metrics/` e `tools/ai_metrics/`
  (tarefa de implementação; sem o `.gitignore` o `report` recusa gravar, comportamento esperado).
  O código de `tools/ai_metrics/` é versionado normalmente.
- Para testar em isolamento, use `--home <pasta temporária>`; nunca use dados reais nos testes.

## 0. Testes automatizados

```powershell
python -m unittest discover -s tools/ai_metrics/tests -t .
python manage.py test tests   # CI existente: não deve descobrir os testes da ferramenta
```

Esperado: tudo verde; a fixture é **sintética**.

## 1. Captura e idempotência (US1, SC-001/002)

```powershell
python -m tools.ai_metrics ingest
python -m tools.ai_metrics ingest      # 2ª vez: "0 registros novos"
python -m tools.ai_metrics verify      # exit 0
```

Uma linha ilegível **no meio** de uma transcrição gera `AVISO ... ilegível(is)` e uma lacuna `unreadable-lines` (a última
linha incompleta é normal e não gera nada).

Esperado: resumo com turnos por sessão e a **divergência** contra `session.cost` por modelo/tipo
(hoje 2%–4% no cache-read); nenhum valor em dinheiro na saída.

## 2. Integridade (SC-003)

1. Copie o histórico de teste, altere um byte de uma linha: `verify` → `exit 2` apontando a `seq`.
2. Remova a última linha: `verify` → `exit 2` (âncora `head.json`).
3. Simule uma queda no meio da gravação (corte o último registro ao meio e volte o `head.json` ao registro anterior):
   `verify` → `exit 0` com "última linha interrompida reparada"; a captura seguinte recria o registro sem duplicar.

## 3. Setup único e hook `Stop` (FR-010, FR-010a/b)

```powershell
python -m tools.ai_metrics setup --dry-run   # mostra a mudança em .claude/settings.local.json
python -m tools.ai_metrics setup             # instala o hook; rodar de novo não duplica
python -m tools.ai_metrics setup --check     # exit 0 = hook e pasta do histórico ok
```

Esperado: as outras chaves de `settings.local.json` continuam intactas (há `.bak`); a partir
daqui o fluxo é só `git switch -c <feature>` → trabalhar. `setup --remove` desfaz só o hook.

- Feche um turno e confira novos registros; force um erro (renomeie a pasta do histórico) e
  confirme que o turno termina normalmente e que `errors.log` recebeu a falha; a captura seguinte
  registra `coverage.gap` `hook-failed`.
- Rode duas capturas ao mesmo tempo (duas janelas): `verify` continua `exit 0`, sem duplicatas (SC-013).
- **T-spike**: registre uma vez o stdin do hook num arquivo temporário para documentar o formato
  (não é usado pelo código).

## 4. Backfill e relatório (US2/US4)

```powershell
python -m tools.ai_metrics backfill
python -m tools.ai_metrics timeline
python -m tools.ai_metrics report 006-telegram-bot --stdout
```

Esperado: 005 e 006 `historical`/`partial`; Pré-Implementação `unknown`; "tokens medidos" (nunca
"total"); ausentes das agregações; seções na ordem Fatos → Métricas → Análise → Evidências →
Limitações; `n` visível; métricas de spec com `n/a` onde não há `tasks.md`.

## 5. Feature nova com uma única ação manual (US3, SC-005)

```powershell
git switch -c 099-exemplo    # a única ação manual
# ... trabalhar normalmente, criar specs/099-*/ pelo Spec Kit ...
python -m tools.ai_metrics report 099-exemplo
```

Esperado: consumo sob `099-exemplo`; alias `specs/099-*` registrado sozinho.

## 6. Correção sem editar histórico (SC-011)

```powershell
python -m tools.ai_metrics feature tag 007-ai-dev-metrics --session 3fdf02d8-a612-4f16-b822-3650bb29d14f --tag setup
python -m tools.ai_metrics verify      # continua exit 0
```

## 7. Análise (US6, SC-009/010)

```powershell
python -m tools.ai_metrics analyze 006-telegram-bot
python -m tools.ai_metrics ingest      # a execução da análise vira "analysis-overhead"
python -m tools.ai_metrics report 006-telegram-bot --stdout   # não inclui esse consumo
```

Esperado: análise aceita com afirmações tipadas e evidências; uma resposta forjada com "porque"
é rejeitada (teste unitário com resposta simulada).

## 8. Privacidade e Git (SC-004, SC-012)

```powershell
git status --short          # nenhum arquivo de .ai-metrics/
git check-ignore .ai-metrics/reports/x.md
```

Varredura: `wal.jsonl` e `.ai-metrics/**` sem texto de prompt/resposta, sem `$`/`USD` de custo, e
sem o valor real de `TELEGRAM_BOT_USERNAME` (procure com o valor **em memória**, não digitado num
comando versionado).

---

## Resultado da validação com dados reais (2026-09-23)

Executada da raiz do repositório com o Python do `.venv` e as transcrições reais do dono; nada de conteúdo de
conversa foi copiado para cá.

| Etapa | Resultado |
|---|---|
| §0 Testes | `tools/ai_metrics`: 210 testes OK. `manage.py test tests` (venv do projeto): 205 testes OK, sem descobrir os testes da ferramenta |
| §1 Captura | `setup` capturou 782 registros de 6 transcrições; repetir a captura gera 0 registros novos; `verify` OK |
| §1 Divergência vs `session.cost` | cache-read entre 0% e 3,6% nas sessões grandes (005: 1,5%; 006: 3,6%); **19,7% (cache-read) e 8,2% (cache-creation) na sessão da conversa de Grill Me**, acima do limite de 5% e sinalizada; o tipo `in` diverge 60–100%, mas vale ~0,001% do total (não gera aviso) |
| §2 Integridade (cópia do histórico) | 1 byte editado → `exit 2` (seq 2); última linha removida → `exit 2` (âncora); linha do meio removida → `exit 2` (seq 101) |
| §3 Hook | comando gravado pelo `setup` roda com exit 0 e sem saída, com cwd diferente, stdin inválido, no bash e no `cmd.exe`. **Disparo real do `Stop` confirmado depois** (T024): dispara em sessão aberta, cwd = raiz do projeto; formato do stdin em `research.md` R4 |
| §4 Backfill | 005 e 006 importadas como `historical`/`partial` (5 e 46 turnos por evidência de caminho/branch dentro da janela dos commits `6d098f9` e `95dbc2a`); Pré-Implementação `unknown`; fora das agregações; idempotente |
| §5 Feature nova | `007-ai-dev-metrics` (branch criado 18:36:48 UTC) apareceu sozinha, com alias `specs/007-ai-dev-metrics` |
| §6 Correção | `feature tag ... --tag setup` na sessão `3fdf02d8`: `verify` continua OK |
| §7 Análise | 1ª execução aceita (afirmações tipadas, evidências, limitações); 2ª rejeitada pelo validador (“porque”), relatório inalterado; consumo das execuções (~9 mil tokens) classificado `analysis-overhead`, fora de qualquer feature |
| §8 Privacidade / Git | varredura de 82 arquivos (histórico, relatórios, arquivos modificados/novos): 0 ocorrências do nome do bot; `git status` sem nada de `.ai-metrics/`; `tools/ai_metrics/` versionável |
| SC-006 | `report --all` (3 features, ~800 turnos) em ~1,1 s |

Achados que mudaram o desenho durante a validação: chamadas `PowerShell` também rodam verificação e commit;
sessões longas atravessam branches, então o ciclo é dividido por feature; o aviso de divergência só vale para
tipos com ≥ 1% dos tokens do modelo.
