"""Captura: transcrições do Claude Code -> eventos do histórico (contracts/wal-events.md).

Regras de privacidade (research R12): nunca grava texto de prompt/resposta/arquivo nem o
comando `Bash`; só contagens, horários, nomes de ferramentas, caminhos relativos e ids.
Idempotente: o que já foi capturado é reconstruído do próprio histórico."""
import hashlib
import json
import re
from pathlib import Path

from tools.ai_metrics import config, gitinfo
from tools.ai_metrics.wal import Wal, canonical, now_iso

LOCAL_COMMANDS = {"model", "help", "config", "cost", "status", "exit", "resume", "agents",
                  "permissions", "login", "logout", "doctor", "mcp", "ide", "vim", "theme"}
CONTEXT_COMMANDS = {"clear": "clear", "compact": "compact"}
TYPES = ("turn", "prompt", "turn.end", "session.cost", "context.event", "coverage.gap",
         "feature.born", "feature.alias")
USAGE_KEYS = (("in", "input_tokens"), ("out", "output_tokens"),
              ("cacheRead", "cache_read_input_tokens"), ("cacheCreate", "cache_creation_input_tokens"))
COST_KEYS = (("in", "inputTokens"), ("out", "outputTokens"), ("cacheRead", "cacheReadInputTokens"),
             ("cacheCreate", "cacheCreationInputTokens"), ("thinking", "thinkingTokens"))
DIVERGENCE_TYPES = ("in", "out", "cacheRead", "cacheCreate")
MATERIAL_SHARE = 0.01   # tipo com menos de 1% dos tokens do modelo não gera aviso de divergência


def slug(path):
    """Nome da pasta de projeto do Claude Code para um diretório."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def default_projects_dir():
    return Path.home() / ".claude" / "projects"


def analysis_cwd(home):
    return Path(home or config.DEFAULT_HOME) / "analysis-cwd"


# ---- leitura -------------------------------------------------------------------------
def read_lines(path):
    """(linhas JSON, números das linhas ilegíveis). A última linha não vazia fica de fora: o Claude Code
    pode estar escrevendo enquanto lemos, então uma linha final incompleta é normal."""
    out, bad, last = [], [], 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            last = n
            try:
                out.append(json.loads(line))
            except ValueError:
                bad.append(n)
    return out, [n for n in bad if n != last]


def _sid(d):
    return d.get("sessionId") or d.get("session_id")


def _count_lines(text):
    return len(text.splitlines()) if isinstance(text, str) and text else 0


def _rel(file_path, repo):
    """Caminho relativo à raiz (posix) ou None se estiver fora do repositório."""
    try:
        p = Path(file_path)
        if not p.is_absolute():
            return p.as_posix()
        return p.resolve().relative_to(Path(repo).resolve()).as_posix()
    except (ValueError, OSError):
        try:
            rel = Path(str(file_path).replace("\\", "/")).relative_to(Path(repo).as_posix())
            return rel.as_posix()
        except ValueError:
            return None


def _classify_bash(command, git_op, cfg, is_error, name="Bash"):
    item = {"name": name}
    for v in cfg["verification_commands"]:
        if re.search(v["pattern"], command or ""):
            item["verify"] = {"id": v["id"], "ok": not is_error}
            break
    for name, pattern in cfg["git_operations"].items():
        if re.search(pattern, command or ""):
            item["git"] = name
            break
    if "git" not in item and isinstance(git_op, dict) and git_op:
        item["git"] = next(iter(git_op))
    return item


def _sanitize_tool(block, result, repo, cfg):
    name, inp = block.get("name"), block.get("input") or {}
    is_error = bool(result and result.get("is_error"))
    if name in ("Bash", "PowerShell"):   # as duas rodam comandos: verificação e commit valem para ambas
        return _classify_bash(inp.get("command"), (result or {}).get("git_op"), cfg, is_error, name)
    item = {"name": name}
    if name in ("Read", "Edit", "Write", "NotebookEdit", "MultiEdit"):
        raw = inp.get("file_path") or inp.get("notebook_path")
        if raw:
            rel = _rel(raw, repo)
            if rel is None:
                item["outside"] = True
            else:
                item["path"] = rel
        if name == "Edit":
            item["add"], item["del"] = _count_lines(inp.get("new_string")), _count_lines(inp.get("old_string"))
        elif name == "MultiEdit":
            edits = [e for e in inp.get("edits") or [] if isinstance(e, dict)]
            item["add"] = sum(_count_lines(e.get("new_string")) for e in edits)
            item["del"] = sum(_count_lines(e.get("old_string")) for e in edits)
        elif name == "Write":
            item["add"], item["del"] = _count_lines(inp.get("content")), 0
    elif name == "Skill" and inp.get("skill"):
        item["skill"] = inp["skill"]
    return item


def _usage(msg):
    u = msg.get("usage") or {}
    out = {k: u[src] for k, src in USAGE_KEYS if isinstance(u.get(src), int)}
    thinking = (u.get("output_tokens_details") or {}).get("thinking_tokens")
    if isinstance(thinking, int):
        out["thinking"] = thinking
    else:
        out["thinking"] = 0
    return out


def _prompt_info(content):
    """(skill, argsKind, texto_de_comando) sem guardar nada do texto."""
    text = content if isinstance(content, str) else " ".join(
        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    m = re.search(r"<command-name>/?([^<\s]+)</command-name>", text)
    skill = m.group(1) if m else None
    args = ""
    a = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
    if a:
        args = a.group(1).strip()
    kind = "none" if not args else ("task-range" if re.search(r"\bT\d{3}\b", args) else "other")
    return skill, kind


# ---- um arquivo de transcrição -> eventos --------------------------------------------
def parse_file(path, repo, cfg, source="claude-code", final=False):
    """Devolve (eventos, adiado, ts_por_sessao, cost_por_sessao, info{unreadable, span})."""
    lines, bad = read_lines(path)
    span = [None, None]
    results, msgs, order = {}, {}, []
    for d in lines:
        if d.get("type") == "user" and isinstance((d.get("message") or {}).get("content"), list):
            for b in d["message"]["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    op = (d.get("toolUseResult") or {}).get("gitOperation") if isinstance(
                        d.get("toolUseResult"), dict) else None
                    results[b.get("tool_use_id")] = {"is_error": bool(b.get("is_error")), "git_op": op}
        if d.get("type") == "assistant":
            m = d.get("message") or {}
            mid = m.get("id")
            if not mid:
                continue
            if mid not in msgs:
                msgs[mid] = []
                order.append(mid)
            msgs[mid].append(d)
    last_msg = order[-1] if order else None

    events, deferred, last_ts, cost = [], False, {}, {}
    perm = {}
    emitted_msgs = set()
    for d in lines:
        typ, sid, ts = d.get("type"), _sid(d), d.get("timestamp")
        if ts:
            span[0] = span[0] or ts
            span[1] = ts
        if sid and ts:
            last_ts[sid] = ts
        if typ == "permission-mode" and sid:
            perm[sid] = d.get("permissionMode")
            continue
        if d.get("permissionMode") and sid:
            perm[sid] = d["permissionMode"]
        if typ == "cost-state" and sid:
            cost[sid] = d
        elif typ == "system" and d.get("subtype") == "turn_duration" and isinstance(d.get("durationMs"), int):
            events.append({"type": "turn.end", "ts": ts, "source": source, "data": {
                "sessionId": sid, "uuid": d.get("uuid"), "parentUuid": d.get("parentUuid"),
                "durationMs": d["durationMs"]}})
        elif typ == "system" and d.get("subtype") == "compact_boundary":
            events.append({"type": "context.event", "ts": ts, "source": source, "data": {
                "sessionId": sid, "uuid": d.get("uuid"), "kind": "compact"}})
        elif typ == "user" and not d.get("isMeta") and (d.get("origin") or {}).get("kind") == "human":
            skill, kind = _prompt_info((d.get("message") or {}).get("content", ""))
            base = skill.split(":")[-1] if skill else None
            if base in CONTEXT_COMMANDS:
                events.append({"type": "context.event", "ts": ts, "source": source, "data": {
                    "sessionId": sid, "uuid": d.get("uuid"), "kind": CONTEXT_COMMANDS[base]}})
            elif base in LOCAL_COMMANDS:
                continue
            else:
                data = {"sessionId": sid, "uuid": d.get("uuid"), "promptId": d.get("promptId"),
                        "gitBranch": d.get("gitBranch"), "argsKind": kind}
                if skill:
                    data["skill"] = skill
                events.append({"type": "prompt", "ts": ts, "source": source, "data": data})
        elif typ == "assistant":
            mid = (d.get("message") or {}).get("id")
            if not mid or mid in emitted_msgs:
                continue
            emitted_msgs.add(mid)
            group = msgs[mid]
            first, msg = group[0], (group[0].get("message") or {})
            if msg.get("model") == "<synthetic>":
                continue
            blocks = [b for g in group for b in (g.get("message") or {}).get("content", [])
                      if isinstance(b, dict) and b.get("type") == "tool_use"]
            missing = any(b.get("id") not in results for b in blocks)
            if missing and mid == last_msg and not final:
                deferred = True
                continue
            tools = [_sanitize_tool(b, results.get(b.get("id")), repo, cfg) for b in blocks]
            data = {"msgId": mid, "sessionId": _sid(first), "uuid": first.get("uuid"),
                    "model": msg.get("model"), "effort": first.get("effort") or first.get("perTurnEffort"),
                    "permissionMode": perm.get(_sid(first)), "gitBranch": first.get("gitBranch"),
                    "sidechain": any(bool(g.get("isSidechain")) for g in group),
                    "stop": (group[-1].get("message") or {}).get("stop_reason"),
                    "usage": _usage(msg), "tools": tools}
            events.append({"type": "turn", "ts": first.get("timestamp"), "source": source, "data": data})
    return events, deferred, last_ts, cost, {"unreadable": len(bad), "span": span}


# ---- dedupe (estado reconstruído do histórico) ---------------------------------------
class Seen:
    def __init__(self, records):
        self.keys = set()
        self.cost = {}
        self.turns = {}  # sessionId -> {model: {tipo: soma}}
        self.span = {}   # sessionId -> [primeiro ts, último ts]
        self.gaps = set()
        self.features = set()
        self.alias_names = set()
        self.alias_owner = {}
        for r in records:
            self.add(r["type"], r["data"], r["ts"])

    @staticmethod
    def key(typ, data):
        if typ == "turn":
            return ("turn", data["msgId"])
        if typ in ("prompt", "turn.end", "context.event"):
            return (typ, data.get("uuid"))
        return None

    def add(self, typ, data, ts):
        k = self.key(typ, data)
        if k:
            self.keys.add(k)
        if typ == "turn":
            tot = self.turns.setdefault(data["sessionId"], {}).setdefault(data["model"], dict.fromkeys(DIVERGENCE_TYPES, 0))
            for t in DIVERGENCE_TYPES:
                tot[t] += data["usage"].get(t, 0)
            span = self.span.setdefault(data["sessionId"], [ts, ts])
            span[0], span[1] = min(span[0], ts), max(span[1], ts)
        elif typ == "session.cost":
            self.cost[data["sessionId"]] = data
        elif typ == "feature.born":
            self.features.add(data["featureId"])
        elif typ == "feature.alias":
            self.alias_names.add(data["alias"])
            self.alias_owner[data["alias"]] = data["featureId"]
        elif typ == "coverage.gap" and data.get("costKey"):
            self.gaps.add((data.get("sessionId"), data["costKey"]))

    def known(self, typ, data):
        k = self.key(typ, data)
        return k in self.keys if k else False


def _cost_data(sid, rec):
    models = {}
    for model, u in (rec.get("modelUsage") or {}).items():
        models[model] = {k: u.get(src, 0) for k, src in COST_KEYS if isinstance(u.get(src, 0), int)}
    return {"sessionId": sid, "models": models, "apiMs": rec.get("totalAPIDuration"),
            "toolMs": rec.get("totalToolDuration"), "totalMs": rec.get("totalDuration"),
            "linesAdded": rec.get("totalLinesAdded"), "linesRemoved": rec.get("totalLinesRemoved")}


def _divergence(informed, captured):
    """{modelo: {tipo: fração}} = (informado - capturado) / informado."""
    out = {}
    for model, inf in informed.items():
        cap = captured.get(model, dict.fromkeys(DIVERGENCE_TYPES, 0))
        out[model] = {t: ((inf[t] - cap[t]) / inf[t]) if inf.get(t) else 0.0
                      for t in DIVERGENCE_TYPES if t in inf}
    return out


# ---- estado e log de erros -----------------------------------------------------------
def _state_path(home):
    return Path(home) / "state.json"


def load_state(home):
    try:
        return json.loads(_state_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(home, state):
    Path(home).mkdir(parents=True, exist_ok=True)
    _state_path(home).write_text(json.dumps(state), encoding="utf-8")


LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def log_error(home, message, context="ingest --hook", level="ERROR"):
    """errors.log: `timestamp<TAB>NÍVEL<TAB>contexto<TAB>mensagem` (uma linha por ocorrência)."""
    try:
        Path(home).mkdir(parents=True, exist_ok=True)
        text = " ".join(str(message).split())
        with open(Path(home) / "errors.log", "a", encoding="utf-8") as fh:
            fh.write(f"{now_iso()}\t{level}\t{context}\t{text}\n")
    except OSError:
        pass


def parse_log_line(line):
    """(ts, nível, contexto, mensagem); aceita o formato antigo `ts<TAB>mensagem` como ERROR."""
    parts = line.split("\t", 3)
    if len(parts) == 4 and parts[1] in LOG_LEVELS:
        return tuple(parts)
    ts, _, msg = line.partition("\t")
    return ts, "ERROR", "legado", msg


def _pending_errors(home, state):
    """Falhas (nível ERROR) do hook ainda não registradas como lacuna: ([(ts, mensagem)], total_de_linhas)."""
    p = Path(home) / "errors.log"
    if not p.exists():
        return [], 0
    lines = [ln for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    parsed = [parse_log_line(ln) for ln in lines[state.get("errors_consumed", 0):]]
    return [(ts, msg) for ts, level, _ctx, msg in parsed if level == "ERROR"], len(lines)


# ---- nascimento de features ----------------------------------------------------------
def _feature_events(repo, cfg, seen, events):
    """`feature.born` para cada branch de feature visto pela primeira vez (research R10).

    Branches em `history_windows` ficam para o `backfill` (histórico parcial)."""
    skip = set(cfg["main_branches"]) | {"HEAD", None} | set(cfg["history_windows"])
    first = {}
    for ev in events:
        if ev["type"] in ("turn", "prompt"):
            branch = ev["data"].get("gitBranch")
            if branch not in skip and branch not in seen.features and branch not in seen.alias_names:
                first[branch] = min(first.get(branch, ev["ts"]), ev["ts"])
    out = []

    def parent_of(branch):
        try:
            parent = gitinfo.moved_from(repo, branch)
        except gitinfo.GitError:
            return None
        return parent if parent in first or parent in seen.features else None

    parents = {b: parent_of(b) for b in first}
    for branch, first_ts in sorted(first.items(), key=lambda kv: kv[1]):
        if parents[branch]:  # criado a partir de um branch de feature (hook do Spec Kit): não é feature nova
            root = parents[branch]
            while parents.get(root):
                root = parents[root]
            seen.alias_names.add(branch)
            out.append({"type": "feature.alias", "ts": first_ts, "source": "git", "data": {
                "featureId": root, "alias": branch, "source": "derived-branch"}})
            continue
        try:
            created = gitinfo.branch_created_at(repo, branch)
        except gitinfo.GitError:
            created = None
        seen.features.add(branch)
        out.append({"type": "feature.born", "ts": created or first_ts, "source": "git" if created else "claude-code",
                    "data": {"featureId": branch, "bornAt": created or first_ts,
                             "bornSource": "reflog" if created else "first-turn",
                             "dataClass": "observed", "coverage": "complete"}})
    out += _spec_aliases(seen, events)
    return out


SPEC_MD = re.compile(r"^(specs/[^/]+)/spec\.md$")


def _spec_aliases(seen, events):
    """`feature.alias` quando o Spec Kit cria `specs/NNN-nome/spec.md` num branch de feature ativo
    (a numeração do branch e a da spec não precisam coincidir)."""
    out = []
    for ev in sorted(events, key=lambda e: e["ts"] or ""):
        if ev["type"] != "turn":
            continue
        owner = ev["data"].get("gitBranch")
        if owner not in seen.features:
            owner = seen.alias_owner.get(owner)
        if not owner:
            continue
        for tool in ev["data"].get("tools", []):
            m = SPEC_MD.match(tool.get("path") or "") if tool["name"] == "Write" else None
            if m and m.group(1) not in seen.alias_names:
                seen.alias_names.add(m.group(1))
                out.append({"type": "feature.alias", "ts": ev["ts"], "source": "claude-code", "data": {
                    "featureId": owner, "alias": m.group(1), "source": "spec-created-on-active-branch"}})
    return out


# ---- execução ------------------------------------------------------------------------
def run(home, repo, projects_dir=None, final=False, cfg=None):
    """Varre as transcrições e grava os eventos novos. Devolve um resumo (dict).

    A trava do histórico é mantida de ponta a ponta (ler o já capturado, decidir, anexar):
    duas capturas simultâneas nunca gravam o mesmo evento duas vezes."""
    home, repo = Path(home or config.DEFAULT_HOME), Path(repo)
    cfg = cfg or config.load(home)
    with Wal(home).lock():
        return _run_locked(home, repo, Path(projects_dir or default_projects_dir()), final, cfg)


def _run_locked(home, repo, projects_dir, final, cfg):
    sources = [(projects_dir / slug(repo), "claude-code"),
               (projects_dir / slug(analysis_cwd(home)), "analysis-overhead")]
    wal = Wal(home)
    state = load_state(home)
    sizes = state.get("sizes", {})
    wal._repair_torn_tail()  # queda anterior no meio da gravação: descarta a meia linha antes de ler
    seen = Seen(wal.read())
    new_events, cost_now, spans, new_sizes = [], {}, {}, dict(sizes)
    fresh = set()
    unreadable = []

    for folder, source in sources:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.jsonl")):
            st = path.stat()
            size = [st.st_size, st.st_mtime_ns]
            if sizes.get(str(path)) == size:  # nada novo (arquivos adiados não guardam o tamanho)
                continue
            events, deferred, last_ts, cost, info = parse_file(path, repo, cfg, source, final)
            if info["unreadable"]:
                unreadable.append((path, source, info))
            for ev in events:
                if not seen.known(ev["type"], ev["data"]):
                    seen.add(ev["type"], ev["data"], ev["ts"])
                    new_events.append(ev)
            for sid, rec in cost.items():
                cost_now[sid] = (rec, last_ts.get(sid) or now_iso(), source)
            if not deferred:
                new_sizes[str(path)] = size
            else:
                new_sizes.pop(str(path), None)

    divergence, warnings = {}, []
    # linhas ilegíveis no meio da transcrição (formato mudou ou arquivo corrompido): aviso + lacuna
    for path, source, info in unreadable:
        key = hashlib.sha1(f"{path.name}:{info['unreadable']}".encode("utf-8")).hexdigest()[:12]
        warnings.append(f"{path.name}: {info['unreadable']} linha(s) ilegível(is) ignorada(s); "
                        "registrada a lacuna unreadable-lines")
        if (path.stem, key) not in seen.gaps:
            seen.gaps.add((path.stem, key))
            first, last = info["span"]
            new_events.append({"type": "coverage.gap", "ts": first or now_iso(), "source": source, "data": {
                "source": "claude-code", "from": first or now_iso(), "to": last or now_iso(),
                "sessionId": path.stem, "reason": "unreadable-lines", "recovered": False,
                "costKey": key, "lines": info["unreadable"]}})
    # session.cost só quando mudou; divergência e lacuna contra o total informado
    threshold = cfg["cost_divergence_threshold_pct"] / 100
    for sid, (rec, ts, source) in cost_now.items():
        data = _cost_data(sid, rec)
        if seen.cost.get(sid) != data:
            new_events.append({"type": "session.cost", "ts": ts, "source": source, "data": data})
            seen.cost[sid] = data
        captured = seen.turns.get(sid, {})
        div = _divergence(data["models"], captured)
        divergence[sid] = div
        cost_key = hashlib.sha1(canonical(data).encode("utf-8")).hexdigest()[:12]
        if any(f > 0 for by in div.values() for f in by.values()) and (sid, cost_key) not in seen.gaps:
            seen.gaps.add((sid, cost_key))
            span = seen.span.get(sid, [ts, ts])
            new_events.append({"type": "coverage.gap", "ts": ts, "source": source, "data": {
                "source": "claude-code", "from": span[0], "to": span[1], "sessionId": sid,
                "reason": "unlogged-api-calls", "recovered": False, "costKey": cost_key,
                "divergence": {m: {t: round(v, 6) for t, v in by.items()} for m, by in div.items()}}})
        if data["models"]:
            main = max(data["models"], key=lambda m: sum(data["models"][m].get(t, 0) for t in DIVERGENCE_TYPES))
            informed_total = sum(data["models"][main].get(t, 0) for t in DIVERGENCE_TYPES) or 1
            for t, frac in div[main].items():
                # só tipos materiais: `in` costuma ser ~0,01% do total e o percentual dele é só ruído
                if frac > threshold and data["models"][main].get(t, 0) / informed_total >= MATERIAL_SHARE:
                    warnings.append(f"sessão {sid}: divergência de {frac:.1%} em {t} ({main}) "
                                    f"acima do limite de {cfg['cost_divergence_threshold_pct']}%")

    new_events += _feature_events(repo, cfg, seen, new_events)

    # falhas anteriores do hook -> lacunas `hook-failed`
    pending, total_lines = _pending_errors(home, state)
    for ts_err, _msg in pending:
        recovered = any(ev["type"] in ("turn", "prompt") for ev in new_events)  # esta captura preencheu o intervalo
        new_events.append({"type": "coverage.gap", "ts": ts_err, "source": "claude-code", "data": {
            "source": "claude-code", "from": ts_err, "to": now_iso(), "reason": "hook-failed",
            "recovered": recovered}})

    written = wal.append(new_events, _locked=True) if new_events else []
    counts = dict.fromkeys(TYPES, 0)
    for r in written:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    state["sizes"] = new_sizes
    if pending or total_lines:
        state["errors_consumed"] = total_lines
    save_state(home, state)
    return {"new": counts, "divergence": divergence, "warnings": warnings, "records": written}


def run_hook(home, repo, projects_dir=None):
    """Modo hook: nunca falha (retorna sempre 0); erros vão para errors.log."""
    try:
        run(home, repo, projects_dir, final=True)
    except BaseException as exc:  # noqa: BLE001 - o hook não pode derrubar o turno
        log_error(home, f"{type(exc).__name__}: {exc}")
    return 0


def summary_text(summary):
    new = summary["new"]
    lines = [f"Registros novos: {sum(new.values())} ("
             + ", ".join(f"{k}={v}" for k, v in new.items() if v) + ")" if sum(new.values())
             else "Registros novos: 0"]
    for sid, by in summary["divergence"].items():
        for model, types in by.items():
            lines.append(f"  sessão {sid[:8]} · {model}: divergência vs total informado — "
                         + ", ".join(f"{t} {f:.1%}" for t, f in types.items()))
    lines += [f"AVISO: {w}" for w in summary["warnings"]]
    return "\n".join(lines)
