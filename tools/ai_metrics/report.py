"""Relatório Markdown por feature: Fatos → Métricas → Análise → Evidências → Limitações.
Frases descritivas e determinísticas; nada aqui afirma causa (FR-040)."""
import re
import statistics
from pathlib import Path

from tools.ai_metrics import config, gitinfo, metrics
from tools.ai_metrics.model import total_tokens
from tools.ai_metrics.wal import now_iso

REPORTS_DIR = ".ai-metrics/reports"
SECTIONS = (("tokens", "Tokens e volume de trabalho"), ("phases", "Fases"),
            ("firstpass", "First-pass"), ("rework", "Retrabalho depois do first-pass"),
            ("volume", "Código executável"), ("context", "Contexto"), ("time", "Tempo do agente"),
            ("spec", "Spec (só Spec Kit)"))


class ReportError(Exception):
    pass


def num(n):
    return f"{n:,}".replace(",", ".") if isinstance(n, int) else str(n)


def fmt(m):
    if m["state"] == "unknown":
        return m["note"] if m["note"] and m["note"].startswith("unknown") else "unknown"
    if m["state"] == "na":
        return m["note"] or "não se aplica"
    v = m["value"]
    if isinstance(v, float):
        v = f"{v:.1%}" if m["unit"] == "razão" else f"{v:g}"
    elif isinstance(v, int):
        v = num(v)
    text = f"{'≥ ' if m['lower'] else ''}{v}" + (f" {m['unit']}" if m["unit"] and m["unit"] != "razão" else "")
    return text + (f" ({m['note']})" if m["note"] else "")


def _dur(ms):
    if ms is None:
        return "unknown"
    s = int(ms / 1000 + 0.5)  # meio para cima (round() arredonda 0,5 para o par)
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return " ".join(x for x in (f"{h} h" if h else "", f"{m} min" if m else "", f"{sec} s" if sec or not (h or m) else "") if x)


def slug_for_file(fid):
    return re.sub(r"[^\w.\-]", "__", fid)


def report_file(repo, fid):
    return Path(repo) / REPORTS_DIR / f"{slug_for_file(fid)}.md"


def write_report(repo, name, text):
    """Grava em .ai-metrics/reports/. Recusa se o diretório não estiver ignorado pelo Git (FR-040b)
    ou se o texto contiver o nome real do bot (Princípio V)."""
    probe = f"{REPORTS_DIR}/{slug_for_file(name)}.md"
    if not gitinfo.check_ignored(repo, probe):
        raise ReportError(".ai-metrics/ não está ignorado pelo Git; adicione `.ai-metrics/` ao .gitignore "
                          "antes de gerar relatórios (os dados de consumo não podem ser publicados).")
    if config.contains_bot_name(text, repo):
        raise ReportError("o relatório conteria o nome real do bot; escrita recusada (Princípio V).")
    path = Path(repo) / probe
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _pct(part, whole):
    return f"{part / whole:.1%}" if whole else "n/d"


def sentences(res):
    """Frases descritivas determinísticas (sem "porque")."""
    f, by = res["facts"], {m["id"]: m for m in res["metrics"]}
    total = by["M-tokens-total"]["value"]
    lower = "≥ " if by["M-tokens-total"]["lower"] else ""
    out = [f"A feature registrou {num(f['turns'])} turnos em {num(f['cycles'])} ciclos e {lower}{num(total)} tokens medidos"
           + (" (mínimo observado)." if lower else ".")]
    pre, imp, post = (by[k] for k in ("M-tokens-preimpl", "M-tokens-impl", "M-tokens-post"))

    def phase(label, m, tail=""):
        return (f"{label} somou {'≥ ' if m['lower'] else ''}{num(m['value'])} tokens medidos "
                f"({_pct(m['value'], total)} da soma capturada){tail}.")

    if pre["state"] == "ok":
        out.append(phase("A Pré-Implementação", pre))
    else:
        out.append("A Pré-Implementação é unknown: " + (
            "parte do trabalho ocorreu fora do Claude Code e não foi medida."
            if f["dataClass"] == "historical" else "nenhuma escrita em artefato executável foi observada."))
    if imp["state"] == "ok":
        out.append(phase("A Implementação, até o first-pass,", imp))
    if post["state"] == "ok":
        out.append(phase("Depois do first-pass, a feature", post))
    elif by["M-first-pass-at"]["state"] == "unknown":
        out.append("O first-pass é unknown: não houve verificação verde nem commit após o início da Implementação.")
    fix = by["M-fix-cycles"]
    if fix["state"] == "ok":
        out.append(f"Foram contados {'≥ ' if fix['lower'] else ''}{fix['value']} ciclos de correção desde o início da Implementação.")
    return out


def render_analysis(analysis):
    if not analysis:
        return "_Nenhuma análise gerada. Use `analyze <feature>` para pedir uma (fatos e métricas apenas)._"
    lines = [f"_Gerada por {analysis['model']} (roteiro v{analysis['promptVersion']}); afirmações tipadas e "
             f"amarradas a métricas._", ""]
    for s in analysis["statements"]:
        ev = ", ".join(s.get("evidence", [])) or "sem evidência"
        lines.append(f"- **{s['type']}**: {s['text']} _(evidência: {ev})_")
    lines += ["", "Limitações apontadas pela análise:"] + [f"- {x}" for x in analysis["limitations"]]
    return "\n".join(lines)


def limitations(model, res):
    f = res["facts"]
    out = ["Estudo observacional e descritivo: nenhuma afirmação causal; `n = 1` feature neste relatório.",
           "Os tokens são os **capturados** das transcrições; a ferramenta de IA informa totais maiores "
           "(chamadas de modelos auxiliares não ficam na transcrição), então os números são mínimos observados.",
           "Fases usam o turno inteiro como unidade; não há divisão de tokens dentro de um turno.",
           "Só há tempo do agente; o intervalo entre ciclos inclui leitura, revisão e ausência.",
           "O workflow é inferido das skills usadas; discussão de requisitos e SDD manual não têm sinal observável.",
           "O encadeamento por hash é evidência de adulteração, não prova (quem refizer o arquivo e a âncora passa)."]
    modes = {}
    for t in res["turns"]:
        modes[t["mode"]] = modes.get(t["mode"], 0) + 1
    out.append("Atribuição dos turnos: " + ", ".join(f"{k}={v}" for k, v in sorted(modes.items())) + ".")
    linked = sum(1 for t in res["turns"] if t.get("draft") == "linked")
    if linked:
        out.append(f"{linked} turnos vieram de uma conversa de descoberta (rascunho) criada antes do branch e "
                   "vinculada por janela de tempo.")
    setup_turns = sum(1 for t in res["turns"] if "setup" in t.get("tags", ()))
    if setup_turns:
        out.append(f"{setup_turns} turnos vêm da conversa marcada `setup`: aparecem neste relatório, mas ficam "
                   "fora das agregações entre workflows.")
    if any(t.get("sidechain") for t in res["turns"]):
        out.append("Há turnos de subagentes (`isSidechain`); a origem deles não foi validada.")
    for g in metrics.touching_gaps(model, f["id"], f, include_recovered=True):
        out.append(f"Lacuna `{g['reason']}` em {g['from']} → {g['to']}"
                   + (" (recuperada)." if g.get("recovered") else " (não recuperada)."))
    if f["dataClass"] == "historical":
        out.append("Feature histórica de cobertura parcial: aparece na linha do tempo e na análise de caso, "
                   "mas fica fora das agregações entre workflows; os tokens são o mínimo observado no Claude Code.")
    if f["lowerBound"]:
        out.append("Valores marcados com `≥` são limites inferiores: a medição toca uma lacuna de cobertura.")
    return out


def render_feature(model, fid, res, analysis=None, position=None):
    f = res["facts"]
    lines = [f"# Relatório: {fid}", "",
             f"_Gerado em {now_iso()} · n = 1 feature · {num(f['turns'])} turnos · {num(f['cycles'])} ciclos_", "",
             "## Fatos", ""]
    facts = [("Feature", f"`{fid}`" + (f" (alias: {', '.join(f'`{a}`' for a in f['aliases'])})" if f["aliases"] else "")),
             ("Workflow", f["workflow"]),
             ("Classe de dado / cobertura", f"{f['dataClass']} / {f['coverageEffective']}"
              + ("" if f["coverageEffective"] == f["coverage"] else f" (declarada: {f['coverage']})")),
             ("Elegível para comparação entre workflows",
              "sim" if f["eligible"] else "não — " + "; ".join(f["eligibleWhy"])),
             ("Nascimento", f"{f['bornAt']} ({f['bornSource']})"),
             ("Ordem cronológica", f"{position[0]} de {position[1]} features" if position else "n/d"),
             ("Modelo(s)", ", ".join(f["models"]) or "unknown"),
             ("Esforço", ", ".join(f["efforts"]) or "unknown"),
             ("Modo de permissão", ", ".join(f["permissionModes"]) or "unknown"),
             ("Período dos turnos", f"{f['firstTurnAt']} → {f['lastTurnAt']}" if f["firstTurnAt"] else "unknown"),
             ("Início da Implementação", f["implementationStartedAt"] or "unknown"),
             ("Primeira escrita em código de produção", f["firstProductionCodeWrite"] or "unknown"),
             ("First-pass", f"{f['firstPassAt']} ({f['firstPassSource']})" if f["firstPassAt"] else "unknown"),
             ("Componentes afetados", ", ".join(f["components"]) or "nenhum")]
    overhead = sum(total_tokens(t) for t in model.turns if t["mode"] == "analysis-overhead")
    if overhead:
        facts.append(("Sobrecarga de análise (fora de qualquer feature)", f"{num(overhead)} tokens medidos"))
    if f.get("status"):
        facts.insert(3, ("Situação", f["status"]))
    lines += [f"- **{k}**: {v}" for k, v in facts]
    lines += ["", "## Métricas", ""]
    lines += [f"- {s}" for s in sentences(res)] + [""]
    for key, title in SECTIONS:
        rows = [m for m in res["metrics"] if m["section"] == key]
        if not rows:
            continue
        lines += [f"### {title}", "", "| Métrica | Valor | Aviso |", "|---|---|---|"]
        for m in rows:
            lines.append(f"| {m['label']} (`{m['id']}`) | {fmt(m)} | {m['warn'] or ''} |")
        lines.append("")
        if key == "time" and f.get("sessionTimes"):
            lines += ["#### Tempo por sessão (informado pela ferramenta)", "",
                      "Sessão inteira, não só esta feature; não é atribuído a ela.", "",
                      "| Sessão | API | Ferramentas | Total |", "|---|---|---|---|"]
            lines += [f"| `{x['sessionId'][:8]}` | {_dur(x['apiMs'])} | {_dur(x['toolMs'])} | {_dur(x['totalMs'])} |"
                      for x in f["sessionTimes"]]
            lines.append("")
    lines += ["## Análise", "", render_analysis(analysis), "", "## Evidências", ""]
    seqs = [t["seq"] for t in res["turns"]]
    if seqs:
        lines.append(f"- Turnos: registros #{min(seqs)}–#{max(seqs)} do histórico "
                     f"(primeiro `{res['turns'][0]['msgId']}`, último `{res['turns'][-1]['msgId']}`).")
    else:
        lines.append("- Nenhum turno atribuído a esta feature.")
    if f["implementationStartedAt"]:
        t0 = next(t for t in res["turns"] if t["ts"] == f["implementationStartedAt"])
        lines.append(f"- Início da Implementação: turno `{t0['msgId']}` (registro #{t0['seq']}).")
    lines += ["", "## Limitações", ""] + [f"- {x}" for x in limitations(model, res)] + [""]
    return "\n".join(lines)


# ---- comparação entre workflows (FR-042, FR-043) ---------------------------------------
WEAK_UNATTRIBUTED_DIFF = 0.15   # diferença (em proporção) entre workflows a partir da qual a comparação é fraca
BIASES = (
    "O workflow é escolhido pelo desenvolvedor (viés de seleção): não há sorteio.",
    "n pequeno: com poucas features por grupo, um caso atípico domina o número.",
    "Aprendizado ao longo do tempo: features mais recentes tendem a ser conduzidas de outro jeito.",
    "Modelo e esforço diferentes entre features mudam o consumo por si só.",
    "Tokens medidos são limites inferiores e ~99% é leitura de cache (contexto × chamadas).",
)


def _tok(turns):
    return sum(total_tokens(t) for t in turns)


def compare(model, repo=None):
    """Dados da comparação: só features elegíveis entram nos agregados; históricas, parciais, em
    andamento e a conversa de `setup` ficam de fora (e são listadas)."""
    cfg, rows = model.cfg, []
    for fid in model.feature_ids():
        res = metrics.compute(model, fid, repo, include_setup=False)
        f, by = res["facts"], {m["id"]: m for m in res["metrics"]}
        rows.append({"id": fid, "workflow": f["workflow"], "status": f["status"], "dataClass": f["dataClass"],
                     "eligible": f["eligible"], "why": f["eligibleWhy"], "turns": f["turns"], "m": by,
                     "tokens": by["M-tokens-total"]["value"]})
    eligible = [r for r in rows if r["eligible"]]
    excluded = [{"id": r["id"], "why": r["why"]} for r in rows if not r["eligible"]]

    classes = {}
    for r in rows:   # classes de custo: features observadas, sem históricas e sem em andamento
        if r["dataClass"] == "observed" and r["status"] in ("entregue", "abandonada"):
            n, tok = classes.get(r["status"], (0, 0))
            classes[r["status"]] = (n + 1, tok + r["tokens"])
    outside, by_session = {}, {}
    for t in model.turns:
        if t["feature"] is None and "setup" not in t["tags"] and t["mode"] != "analysis-overhead":
            klass = model.cost_class(t)
            n, tok = outside.get(klass, (0, 0))
            outside[klass] = (n + 1, tok + total_tokens(t))
            by_session.setdefault(t["sessionId"], []).append(t)
    classes.update(outside)
    overhead = sum(total_tokens(t) for t in model.turns if t["mode"] == "analysis-overhead")

    un_tokens = {}
    for sid, turns in by_session.items():
        ids = {t["seq"] for t in turns}
        cycles = [c for c in model.cycles if c["sessionId"] == sid and c["feature"] is None]
        wf = metrics.workflow_of(cycles, turns, cfg)
        un_tokens[wf] = un_tokens.get(wf, 0) + _tok(turns)
    attributed = {}
    for r in rows:
        if r["dataClass"] == "observed":
            attributed[r["workflow"]] = attributed.get(r["workflow"], 0) + r["tokens"]
    share = {}
    for wf in set(un_tokens) | set(attributed):
        total = un_tokens.get(wf, 0) + attributed.get(wf, 0)
        share[wf] = (un_tokens.get(wf, 0) / total) if total else 0.0
    weak = len(share) >= 2 and (max(share.values()) - min(share.values())) > WEAK_UNATTRIBUTED_DIFF
    return {"rows": rows, "eligible": eligible, "excluded": excluded, "classes": classes,
            "overhead": overhead, "unattributed_share": share, "weak": weak}


def _median_cell(rows, mid):
    vals = [r["m"][mid]["value"] for r in rows if r["m"][mid]["state"] == "ok"]
    if not vals:
        return "unknown"
    lower = any(r["m"][mid]["lower"] for r in rows if r["m"][mid]["state"] == "ok")
    med = statistics.median(vals)
    return f"{'≥ ' if lower else ''}{num(round(med)) if med >= 10 else f'{med:g}'}"


def render_comparison(data, model=None):
    el = data["eligible"]
    lines = ["# Comparação entre workflows", "",
             f"_Gerada em {now_iso()} · n = {len(el)} features elegíveis · estudo observacional e descritivo_", "",
             "Números brutos primeiro; nenhuma afirmação causal. Só entram features observadas, completas e "
             "com situação entregue ou abandonada.", "", "## Por workflow", "",
             "| Workflow | n | Tokens medidos (mediana) | Pré-Implementação (mediana) | Ciclos de correção (mediana) |",
             "|---|---|---|---|---|"]
    for wf in ("direct", "grill", "speckit", "grill+speckit"):
        grp = [r for r in el if r["workflow"] == wf]
        if grp:
            lines.append(f"| {wf} | {len(grp)} | {_median_cell(grp, 'M-tokens-total')} | "
                         f"{_median_cell(grp, 'M-tokens-preimpl')} | {_median_cell(grp, 'M-fix-cycles')} |")
    lines += ["", "## Features elegíveis (números brutos)", "",
              "| Feature | Workflow | Situação | Tokens medidos | Pré-Implementação | Ciclos até o first-pass | "
              "Ciclos de correção | Post-First-Pass (razão) | Tempo do agente |", "|---|---|---|---|---|---|---|---|---|"]
    for r in el:
        m = r["m"]
        lines.append(f"| `{r['id']}` | {r['workflow']} | {r['status']} | {fmt(m['M-tokens-total'])} | "
                     f"{fmt(m['M-tokens-preimpl'])} | {fmt(m['M-cycles-until-fp'])} | {fmt(m['M-fix-cycles'])} | "
                     f"{fmt(m['M-post-fp-ratio'])} | {fmt(m['M-agent-seconds'])} |")
    if not el:
        lines.append("| _nenhuma feature elegível ainda_ | | | | | | | | |")
    lines += ["", "## Classes de custo (separadas)", "", "| Classe | n | Tokens medidos |", "|---|---|---|"]
    for klass in ("entregue", "abandonada", "exploração sem entrega", "unattributed"):
        n, tok = data["classes"].get(klass, (0, 0))
        lines.append(f"| {klass} | {n} | ≥ {num(tok)} |")
    lines.append("")
    lines.append(f"Sobrecarga de análise (fora de qualquer feature): {num(data['overhead'])} tokens medidos.")
    lines += ["", "## Proporção de unattributed por workflow", "", "| Workflow | Proporção |", "|---|---|"]
    for wf, share in sorted(data["unattributed_share"].items()):
        lines.append(f"| {wf} | {share:.1%} |")
    if data["weak"]:
        lines += ["", "**comparação fraca**: a proporção de consumo `unattributed` difere muito entre workflows "
                      f"(mais de {WEAK_UNATTRIBUTED_DIFF:.0%}); os grupos não estão medidos com a mesma completude."]
    lines += ["", "## Fora da comparação", ""]
    lines += [f"- `{x['id']}`: {'; '.join(x['why'])}" for x in data["excluded"]] or ["- nenhuma"]
    lines += ["", "## Vieses conhecidos", ""] + [f"- {b}" for b in BIASES] + [""]
    return "\n".join(lines)
