"""Métricas de uma feature, derivadas do histórico (data-model.md). Só números e rótulos:
nada aqui afirma causa. Ausência de medição é `unknown`; sem spec é `não se aplica`."""
import fnmatch
import re
import statistics

from tools.ai_metrics import config, gitinfo
from tools.ai_metrics.model import seconds_between

WRITE_TOOLS = ("Edit", "Write", "NotebookEdit", "MultiEdit")
PLANNING_SKILLS = ("speckit-plan", "speckit-tasks", "speckit-analyze", "speckit-checklist")
TOKEN_TYPES = ("in", "out", "cacheRead", "cacheCreate")

WARNINGS = {
    "tokens": "cerca de 99% costuma ser leitura de cache: o total mede contexto × número de chamadas.",
    "preimpl": "um Grill Me caro pode valer a pena; o número sozinho não diz isso.",
    "post-fp-ratio": "depende do estilo dos prompts e da regra de ciclo.",
    "fix-cycles": "em TDD, falhas seguintes ao primeiro vermelho esperado ainda contam e podem inflar o número.",
    "churn": "refatoração legítima e arquivos grandes inflam o churn.",
    "per-line": "linha não é complexidade (migrações e boilerplate).",
    "plan-path": "testes e arquivos não previstos derrubam a precisão sem ser erro.",
    "spec-changes": "se os documentos acompanham o código, isto é política, não defeito.",
    "gap": "o intervalo entre ciclos inclui leitura, revisão e ausência.",
}


def metric(mid, label, value, unit="", state="ok", warn=None, section="", note=None):
    """`state`: ok | unknown | na (não se aplica). `lower` (limite inferior, ≥) entra na fase de cobertura."""
    return {"id": mid, "label": label, "value": value, "unit": unit, "state": state,
            "lower": False, "warn": WARNINGS.get(warn) if warn else None, "section": section, "note": note}


def unknown(mid, label, unit="", section="", note="unknown"):
    return metric(mid, label, None, unit, "unknown", section=section, note=note)


def not_applicable(mid, label, unit="", section="", note="não se aplica"):
    return metric(mid, label, None, unit, "na", section=section, note=note)


# ---- auxiliares ----------------------------------------------------------------------
def tools_of(turn):
    return turn.get("tools", [])


def exec_writes(turn, cfg):
    return [t for t in tools_of(turn) if t["name"] in WRITE_TOOLS and t.get("path")
            and config.is_executable(t["path"], cfg)]


def spec_writes(turn):
    return [t for t in tools_of(turn) if t["name"] in WRITE_TOOLS and t.get("path")
            and config.match_any(t["path"], ["specs/**"])]


def tokens(turns):
    """({tipo: soma}, faltou_algum_campo). Campo ausente conta como desconhecido, não como zero."""
    tot, missing = dict.fromkeys(TOKEN_TYPES, 0), False
    for t in turns:
        for k in TOKEN_TYPES:
            if k in t["usage"]:
                tot[k] += t["usage"][k]
            else:
                missing = True
    return tot, missing


def cycle_calls(cycle):
    return [(t, tool) for t in cycle["turns"] for tool in tools_of(t)]


def last_verification(cycle):
    v = [tool["verify"]["ok"] for _, tool in cycle_calls(cycle) if tool.get("verify")]
    return v[-1] if v else None


def has_commit(cycle):
    return any(tool.get("git") == "commit" for _, tool in cycle_calls(cycle))


def skill_of(cycle):
    return (cycle["prompt"] or {}).get("skill")


def workflow_of(cycles, turns, cfg):
    labels = cfg["skill_labels"]
    used = {skill_of(c) for c in cycles if skill_of(c)}
    used |= {tool["skill"] for t in turns for tool in tools_of(t) if tool.get("skill")}
    has = {k: any(fnmatch.fnmatchcase(s, g) for s in used for g in globs) for k, globs in labels.items()}
    if has.get("speckit") and has.get("grill"):
        return "grill+speckit"
    return "speckit" if has.get("speckit") else "grill" if has.get("grill") else "direct"


# ---- fases ---------------------------------------------------------------------------
def implementation_start(turns, cfg):
    """(índice do turno da 1ª escrita executável, índice da 1ª escrita em código de produção)."""
    impl = prod = None
    for i, t in enumerate(turns):
        writes = exec_writes(t, cfg)
        if writes and impl is None:
            impl = i
        if prod is None and any(config.match_any(w["path"], cfg["production_paths"]) for w in writes):
            prod = i
    return impl, prod


def pre_label(turn, cycle_skill, cfg):
    """Rótulo de custo de um turno de Pré-Implementação (ordem: spec > grill > planejamento > outros)."""
    if spec_writes(turn):
        return "spec"
    if cycle_skill and any(fnmatch.fnmatchcase(cycle_skill, g) for g in cfg["skill_labels"].get("grill", [])):
        return "grill"
    if cycle_skill in PLANNING_SKILLS or any(t["name"] == "ExitPlanMode" for t in tools_of(turn)):
        return "planning"
    return "other"


def active_skill_by_turn(cycles):
    """Skill "ativa" de cada turno: a do último prompt com skill na mesma sessão (rótulo aproximado)."""
    out, active = {}, {}
    for c in sorted(cycles, key=lambda c: c["startedAt"]):
        if skill_of(c):
            active[c["sessionId"]] = skill_of(c)
        for t in c["turns"]:
            out[t["seq"]] = active.get(c["sessionId"])
    return out


# ---- first-pass ----------------------------------------------------------------------
def first_pass(cycles, impl_ts, fid, fp_events):
    """(ciclo, fonte, índice_do_ciclo_de_início). Sem verificação verde nem commit: (None, 'unknown', ...)."""
    start = next((i for i, c in enumerate(cycles) if any(t["ts"] == impl_ts for t in c["turns"])), None)
    corrections = [e for e in fp_events if e["featureId"] == fid]
    if corrections:
        e = max(corrections, key=lambda x: x["seq"])
        if e.get("cycleUuid") is None:
            return None, "unknown (corrigido)", start
        c = next((c for c in cycles if (c["prompt"] or {}).get("uuid") == e["cycleUuid"]), None)
        return c, "corrected", start
    if start is None:
        return None, "unknown", None
    cand = cycles[start:]
    structural = [c for c in cand if skill_of(c) == "speckit-implement"
                  and (c["prompt"] or {}).get("argsKind") != "task-range"]
    delivery, kind = (structural, "feature-delivery") if structural else (cand[:1], "assumed")
    for c in delivery:
        if last_verification(c) is True:
            return c, f"verified-green ({kind})", start
        if has_commit(c):
            return c, f"commit-proxy ({kind})", start
    return None, "unknown", start


def fix_cycles(cycles, cfg):
    """Ciclos de correção (FR-030): verificação que falhou seguida de edição, exceto o primeiro
    vermelho esperado logo após escrever um teste no mesmo ciclo (sem produção antes)."""
    count, pending_fail = 0, False
    for c in cycles:
        test_pending = False
        for _, tool in cycle_calls(c):
            path = tool.get("path")
            if tool["name"] in WRITE_TOOLS and path and config.is_executable(path, cfg):
                if pending_fail:
                    count, pending_fail = count + 1, False
                test_pending = config.match_any(path, cfg["test_paths"])
            elif tool.get("verify"):
                if tool["verify"]["ok"]:
                    pending_fail = False
                elif test_pending:
                    test_pending = False
                else:
                    pending_fail = True
    return count


# ---- spec ----------------------------------------------------------------------------
def planned_paths(text, cfg):
    found = re.findall(r"[\w./\-]+/[\w.\-]+\.\w{1,5}", text or "")
    return {p.lstrip("./") for p in found if config.is_executable(p.lstrip("./"), cfg)}


def spec_dir(model, fid):
    for alias in model.aliases_of(fid):
        if alias.startswith("specs/"):
            return alias.rstrip("/")
    return None


# ---- cálculo principal ---------------------------------------------------------------
def compute(model, fid, repo=None, include_setup=True):
    """`include_setup=False` tira a conversa marcada `setup` (comparações entre workflows)."""
    cfg, repo = model.cfg, repo or model.repo
    info = model.features[fid]
    turns = model.turns_of(fid, include_setup)
    keep = {t["seq"] for t in turns}
    cycles = [c for c in model.cycles_of(fid) if not c["turns"] or any(t["seq"] in keep for t in c["turns"])]
    facts = {"id": fid, "aliases": model.aliases_of(fid), "bornAt": info["bornAt"],
             "bornSource": info.get("bornSource"), "dataClass": info.get("dataClass", "observed"),
             "coverage": info.get("coverage", "complete"),
             "workflow": model.workflow_override.get(fid) or workflow_of(cycles, turns, cfg),
             "status": model.status(fid),
             "turns": len(turns), "cycles": len(cycles),
             "models": sorted({t["model"] for t in turns}),
             "efforts": sorted({t["effort"] for t in turns if t.get("effort")}),
             "permissionModes": sorted({t["permissionMode"] for t in turns if t.get("permissionMode")}),
             "sessions": sorted({t["sessionId"] for t in turns}),
             "firstTurnAt": turns[0]["ts"] if turns else None, "lastTurnAt": turns[-1]["ts"] if turns else None}
    m = []
    total, miss = tokens(turns)
    m.append(metric("M-turns", "Turnos (respostas do assistente)", len(turns), "turnos", section="tokens"))
    m.append(metric("M-cycles", "Ciclos (prompt humano → fim do trabalho do agente)", len(cycles), "ciclos", section="tokens"))
    for k, label in (("in", "entrada"), ("out", "saída"), ("cacheRead", "leitura de cache"),
                     ("cacheCreate", "criação de cache")):
        m.append(metric(f"M-tokens-{k}", f"Tokens de {label}", total[k], "tokens", section="tokens"))
    m.append(metric("M-tokens-total", "Tokens medidos (soma capturada)", sum(total.values()), "tokens",
                    warn="tokens", section="tokens"))

    impl_i, prod_i = implementation_start(turns, cfg)
    impl_ts = turns[impl_i]["ts"] if impl_i is not None else None
    facts["implementationStartedAt"] = impl_ts
    facts["firstProductionCodeWrite"] = turns[prod_i]["ts"] if prod_i is not None else None
    fp_cycle, fp_source, start_i = first_pass(cycles, impl_ts, fid, model.fp_events) if impl_ts else (None, "unknown", None)
    fp_at = fp_cycle["endedAt"] if fp_cycle else None
    facts["firstPassAt"], facts["firstPassSource"] = fp_at, fp_source

    pre = turns[:impl_i] if impl_i is not None else turns
    rest = turns[impl_i:] if impl_i is not None else []
    if fp_at:
        impl_phase = [t for t in rest if t["ts"] <= fp_at]
        post = [t for t in rest if t["ts"] > fp_at]
    else:
        impl_phase, post = rest, []
    for mid, label, group, known in (("preimpl", "Pré-Implementação", pre, True),
                                     ("impl", "Implementação (até o first-pass)", impl_phase, impl_i is not None),
                                     ("post", "Pós-First-Pass", post, fp_at is not None)):
        if known:
            m.append(metric(f"M-tokens-{mid}", f"Tokens — {label}", sum(tokens(group)[0].values()), "tokens",
                            warn="preimpl" if mid == "preimpl" else None, section="phases"))
        else:
            m.append(unknown(f"M-tokens-{mid}", f"Tokens — {label}", "tokens", "phases"))
    active = active_skill_by_turn(cycles)
    sub = dict.fromkeys(("spec", "grill", "planning", "other"), 0)
    for t in pre:
        sub[pre_label(t, active.get(t["seq"]), cfg)] += sum(tokens([t])[0].values())
    for k, label in (("spec", "Spec Artifact Cost (turnos que escrevem em specs/**)"), ("grill", "Grill Cost"),
                     ("planning", "Planning Cost"), ("other", "Outros")):
        m.append(metric(f"M-pre-{k}", f"Pré-Implementação — {label}", sub[k], "tokens", section="phases"))
    m.append(metric("M-impl-start", "Início da Implementação", impl_ts, "", "ok" if impl_ts else "unknown",
                    section="phases", note=None if impl_ts else "unknown (nenhuma escrita em artefato executável)"))
    m.append(metric("M-first-prod-write", "Primeira escrita em código de produção", facts["firstProductionCodeWrite"], "",
                    "ok" if prod_i is not None else "unknown", section="phases"))

    # first-pass e retrabalho (métricas contínuas; sem indicador binário)
    m.append(metric("M-first-pass-at", "First-pass (fim do primeiro ciclo de entrega verificado)", fp_at, "",
                    "ok" if fp_at else "unknown", section="firstpass",
                    note=f"fonte: {fp_source}"))
    if fp_cycle is not None and start_i is not None:
        upto = cycles.index(fp_cycle) - start_i + 1
        m.append(metric("M-cycles-until-fp", "Ciclos até o first-pass", upto, "ciclos", section="firstpass"))
    else:
        m.append(unknown("M-cycles-until-fp", "Ciclos até o first-pass", "ciclos", "firstpass"))
    impl_cycles = cycles[start_i:] if start_i is not None else []
    if impl_cycles:
        m.append(metric("M-fix-cycles", "Ciclos de correção (verificação falhou → edição)", fix_cycles(impl_cycles, cfg),
                        "ciclos", warn="fix-cycles", section="rework"))
    else:
        m.append(unknown("M-fix-cycles", "Ciclos de correção (verificação falhou → edição)", "ciclos", "rework"))
    if fp_at:
        post_tok = sum(tokens(post)[0].values())
        all_tok = sum(total.values())
        before = {w["path"] for t in impl_phase for w in exec_writes(t, cfg)} | \
                 {w["path"] for t in pre for w in exec_writes(t, cfg)}
        post_w = [w for t in post for w in exec_writes(t, cfg)]
        post_cycles = cycles[cycles.index(fp_cycle) + 1:]
        m.append(metric("M-post-fp-tokens", "Post-First-Pass Cost (tokens)", post_tok, "tokens", section="rework"))
        m.append(metric("M-post-fp-ratio", "Post-First-Pass Cost (razão sobre o total medido)",
                        round(post_tok / all_tok, 4) if all_tok else None, "razão",
                        "ok" if all_tok else "unknown", warn="post-fp-ratio", section="rework"))
        m.append(metric("M-post-fp-churn", "Post-First-Pass Churn (linhas escritas em executáveis)",
                        sum(w.get("add", 0) + w.get("del", 0) for w in post_w), "linhas", warn="churn", section="rework"))
        m.append(metric("M-post-fp-fix-cycles", "Ciclos de correção após o first-pass",
                        fix_cycles(post_cycles, cfg), "ciclos", warn="fix-cycles", section="rework"))
        m.append(metric("M-human-turns-post-fp", "Turnos humanos após o first-pass",
                        sum(1 for c in post_cycles if c["prompt"]), "prompts", section="rework"))
        m.append(metric("M-reedited-files", "Arquivos executáveis já modificados e alterados de novo",
                        len({w["path"] for w in post_w} & before), "arquivos", section="rework"))
    else:
        for mid, label, unit in (("M-post-fp-tokens", "Post-First-Pass Cost (tokens)", "tokens"),
                                 ("M-post-fp-ratio", "Post-First-Pass Cost (razão sobre o total medido)", "razão"),
                                 ("M-post-fp-churn", "Post-First-Pass Churn (linhas escritas em executáveis)", "linhas"),
                                 ("M-post-fp-fix-cycles", "Ciclos de correção após o first-pass", "ciclos"),
                                 ("M-human-turns-post-fp", "Turnos humanos após o first-pass", "prompts"),
                                 ("M-reedited-files", "Arquivos executáveis já modificados e alterados de novo", "arquivos")):
            m.append(unknown(mid, label, unit, "rework"))

    # volume de código (contagens das chamadas de ferramenta)
    writes = [w for t in turns for w in exec_writes(t, cfg)]
    files = sorted({w["path"] for w in writes})
    m.append(metric("M-lines-added", "Linhas executáveis escritas (adicionadas)", sum(w.get("add", 0) for w in writes),
                    "linhas", section="volume"))
    m.append(metric("M-lines-removed", "Linhas executáveis removidas", sum(w.get("del", 0) for w in writes),
                    "linhas", section="volume"))
    m.append(metric("M-exec-files", "Arquivos executáveis alterados", len(files), "arquivos", section="volume"))
    facts["components"] = sorted({p.split("/")[1] if p.startswith("apps/") and p.count("/") > 1 else p.split("/")[0]
                                  for p in files})
    total_lines = sum(w.get("add", 0) for w in writes)
    m.append(metric("M-tokens-per-line", "Tokens medidos por linha executável escrita (secundária)",
                    round(sum(total.values()) / total_lines) if total_lines else None, "tokens/linha",
                    "ok" if total_lines else "unknown", warn="per-line", section="volume"))

    # contexto
    sizes = [t["usage"].get("in", 0) + t["usage"].get("cacheRead", 0) + t["usage"].get("cacheCreate", 0) for t in turns]
    reads = [tool["path"] for t in turns for tool in tools_of(t) if tool["name"] == "Read" and tool.get("path")]
    sessions = facts["sessions"]
    span = (facts["firstTurnAt"], facts["lastTurnAt"])
    ctx = [c for c in model.contexts if c["sessionId"] in sessions and turns and span[0] <= c["ts"] <= span[1]]
    m.append(metric("M-ctx-peak", "Contexto por chamada — pico", max(sizes) if sizes else None, "tokens",
                    "ok" if sizes else "unknown", section="context"))
    m.append(metric("M-ctx-mean", "Contexto por chamada — média", round(statistics.fmean(sizes)) if sizes else None,
                    "tokens", "ok" if sizes else "unknown", section="context"))
    m.append(metric("M-files-read", "Arquivos distintos lidos", len(set(reads)), "arquivos", section="context"))
    m.append(metric("M-reads", "Leituras de arquivo (volume)", len(reads), "leituras", section="context"))
    m.append(metric("M-ctx-events", "Compactações e /clear no período", len(ctx), "eventos", section="context"))

    # tempo do agente (nunca "tempo humano")
    secs = sum(c["durationMs"] for c in cycles) / 1000
    m.append(metric("M-agent-seconds", "Tempo do agente (prompt → fim do trabalho)", round(secs), "s",
                    section="time", note="estimado em parte dos ciclos" if any(c["estimated"] for c in cycles) else None))
    idle_s = cfg["idle_minutes"] * 60
    gaps = [seconds_between(a["endedAt"], b["startedAt"]) for a, b in zip(cycles, cycles[1:])]
    active_gaps = [g for g in gaps if 0 <= g < idle_s]
    m.append(metric("M-gap-median", "Intervalo entre ciclos, mediana (inclui leitura, revisão e ausência)",
                    round(statistics.median(active_gaps)) if active_gaps else None, "s",
                    "ok" if active_gaps else "unknown", warn="gap", section="time"))
    m.append(metric("M-idle-gaps", f"Intervalos ociosos (≥ {cfg['idle_minutes']} min)", sum(1 for g in gaps if g >= idle_s),
                    "intervalos", section="time"))
    # tempo de API e de ferramenta: só por sessão (sessão inteira, não atribuível à feature) e fora dos M-*
    facts["sessionTimes"] = [
        {"sessionId": sid, "apiMs": c.get("apiMs"), "toolMs": c.get("toolMs"), "totalMs": c.get("totalMs")}
        for sid, c in sorted(model.costs.items()) if sid in facts["sessions"]]

    # spec (só Spec Kit): "não se aplica" sem spec, nunca 0
    sdir = spec_dir(model, fid)
    if sdir is None:
        for mid, label, unit in (("M-plan-recall", "Plan Path Coverage — recall", "razão"),
                                 ("M-plan-precision", "Plan Path Coverage — precisão", "razão"),
                                 ("M-spec-changes-turns", "Spec Changes After Implementation Start — turnos", "turnos"),
                                 ("M-spec-changes-tokens", "Spec Changes After Implementation Start — tokens", "tokens")):
            m.append(not_applicable(mid, label, unit, "spec", "não se aplica (feature sem spec)"))
    else:
        text = None
        if repo is not None:
            try:
                text = gitinfo.show_file(repo, fid, cfg["main_branches"][0], f"{sdir}/tasks.md")
            except gitinfo.GitError:
                text = None
        planned = planned_paths(text, cfg) if text else set()
        changed = set()
        if repo is not None:
            try:
                changed = {p for p in gitinfo.changed_files(repo, fid, cfg["main_branches"][0])
                           if config.is_executable(p, cfg)}
            except gitinfo.GitError:
                pass
        hit = len(planned & changed)
        m.append(metric("M-plan-recall", "Plan Path Coverage — recall", round(hit / len(planned), 4) if planned and changed else None,
                        "razão", "ok" if planned and changed else "na", warn="plan-path", section="spec",
                        note=None if planned and changed else "não se aplica (sem tasks.md ou sem diff)"))
        m.append(metric("M-plan-precision", "Plan Path Coverage — precisão", round(hit / len(changed), 4) if planned and changed else None,
                        "razão", "ok" if planned and changed else "na", warn="plan-path", section="spec",
                        note=None if planned and changed else "não se aplica (sem tasks.md ou sem diff)"))
        if impl_ts:
            late = [t for t in rest if spec_writes(t)]
            m.append(metric("M-spec-changes-turns", "Spec Changes After Implementation Start — turnos", len(late),
                            "turnos", warn="spec-changes", section="spec"))
            m.append(metric("M-spec-changes-tokens", "Spec Changes After Implementation Start — tokens",
                            sum(sum(tokens([t])[0].values()) for t in late), "tokens", warn="spec-changes", section="spec"))
        else:
            m.append(unknown("M-spec-changes-turns", "Spec Changes After Implementation Start — turnos", "turnos", "spec"))
            m.append(unknown("M-spec-changes-tokens", "Spec Changes After Implementation Start — tokens", "tokens", "spec"))
    apply_coverage(model, fid, facts, m, turns)
    ok, why = eligibility(model, fid, facts)
    facts["eligible"], facts["eligibleWhy"] = ok, why
    return {"facts": facts, "metrics": m, "totals": total, "turns": turns, "cycles": cycles,
            "phase_turns": {"pre": pre, "impl": impl_phase, "post": post}}


# ---- cobertura (FR-035, FR-036, FR-039) ------------------------------------------------
TOKEN_UNITS = {"tokens", "tokens/linha"}
ADDITIVE_UNITS = {"turnos", "ciclos", "linhas", "arquivos", "leituras", "prompts", "s", "eventos", "intervalos"}
NON_ADDITIVE = {"M-gap-median", "M-ctx-peak", "M-ctx-mean"}
SYSTEMATIC_GAP = "unlogged-api-calls"   # divergência pequena e sempre presente: marca tokens, não a feature


def touching_gaps(model, fid, facts, include_recovered=False):
    """Lacunas (por padrão só as NÃO recuperadas) que tocam a feature: por feature, sessão ou intervalo."""
    first, last, sessions = facts["firstTurnAt"], facts["lastTurnAt"], set(facts["sessions"])
    out = []
    for g in model.gaps:
        if g.get("recovered") and not include_recovered:
            continue
        if g.get("featureId") == fid or (g.get("sessionId") and g["sessionId"] in sessions):
            out.append(g)
        elif not g.get("sessionId") and not g.get("featureId") and first and g["from"] <= last and g["to"] >= first:
            out.append(g)
    return out


def apply_coverage(model, fid, facts, metrics_list, turns):
    gaps = touching_gaps(model, fid, facts)
    partial = facts["dataClass"] == "historical" or facts["coverage"] == "partial"
    broad = partial or any(g["reason"] != SYSTEMATIC_GAP for g in gaps)
    token_lower = broad or bool(gaps)
    facts["gaps"] = [(g["reason"], bool(g.get("recovered"))) for g in gaps]
    facts["coverageEffective"] = "partial" if broad else "complete"
    facts["lowerBound"] = token_lower
    if partial and facts["dataClass"] == "historical":
        for i, x in enumerate(metrics_list):   # a especificação rodou fora do Claude Code: unknown, nunca 0
            if x["id"] in ("M-tokens-preimpl", "M-pre-spec", "M-pre-grill", "M-pre-planning", "M-pre-other"):
                metrics_list[i] = unknown(x["id"], x["label"], x["unit"], x["section"],
                                          "unknown (a especificação rodou fora do Claude Code)")
    for x in metrics_list:
        if x["state"] != "ok":
            continue
        if x["id"] in NON_ADDITIVE:
            continue
        if x["unit"] in TOKEN_UNITS and token_lower:
            x["lower"] = True
        elif x["unit"] in ADDITIVE_UNITS and broad:
            x["lower"] = True


def eligibility(model, fid, facts=None):
    """Elegível para comparação: observada + completa (sem lacuna não recuperada além da sistemática)
    + situação entregue ou abandonada. Devolve (bool, [motivos])."""
    info = model.features[fid]
    if facts is None:
        turns = model.turns_of(fid)
        facts = {"firstTurnAt": turns[0]["ts"] if turns else None, "lastTurnAt": turns[-1]["ts"] if turns else None,
                 "sessions": sorted({t["sessionId"] for t in turns})}
    why = []
    if info.get("dataClass", "observed") == "historical":
        why.append("feature histórica (dado parcial)")
    if info.get("coverage", "complete") == "partial":
        why.append("cobertura parcial")
    if any(g["reason"] != SYSTEMATIC_GAP for g in touching_gaps(model, fid, facts)):
        why.append("lacuna de cobertura não recuperada")
    if model.status(fid) == "em andamento":
        why.append("situação: em andamento")
    if not model.turns_of(fid):
        why.append("sem turnos")
    return (not why), why
