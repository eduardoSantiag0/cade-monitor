"""Camada derivada: features, ciclos, atribuição, rascunhos e situação, calculados a cada
relatório a partir do histórico (nada disto é gravado). Contrato: data-model.md."""
import re
from datetime import datetime, timedelta, timezone

from tools.ai_metrics import config, gitinfo
from tools.ai_metrics.wal import Wal

KIND_ORDER = {"prompt": 0, "turn": 1, "end": 2}


def parse_ts(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def seconds_between(a, b):
    return (parse_ts(b) - parse_ts(a)).total_seconds()


def total_tokens(turn):
    u = turn["usage"]
    return sum(u.get(k, 0) for k in ("in", "out", "cacheRead", "cacheCreate"))


class Model:
    def __init__(self, records, cfg, repo=None, now=None):
        self.cfg, self.repo = cfg, repo
        self.now = now or datetime.now(timezone.utc)
        self._status = {}
        self.records = records
        self.turns, self.prompts, self.ends = [], [], []
        self.costs, self.gaps, self.contexts = {}, [], []
        self.features, self.aliases = {}, {}
        self.attr_events, self.status_events, self.fp_events, self.analyses = [], [], [], []
        for r in records:
            item = dict(r["data"], ts=r["ts"], seq=r["seq"], source=r["source"])
            t = r["type"]
            if t == "turn":
                self.turns.append(item)
            elif t == "prompt":
                self.prompts.append(item)
            elif t == "turn.end":
                self.ends.append(item)
            elif t == "session.cost":
                self.costs[item["sessionId"]] = item
            elif t == "coverage.gap":
                self.gaps.append(item)
            elif t == "context.event":
                self.contexts.append(item)
            elif t == "feature.born":
                self.features[item["featureId"]] = item  # o último evento vence
            elif t == "feature.alias":
                self.aliases[item["alias"]] = item
            elif t in ("attribution.set", "attribution.corrected"):
                item["kind"] = t
                self.attr_events.append(item)
            elif t == "status.corrected":
                self.status_events.append(item)
            elif t == "firstPass.corrected":
                self.fp_events.append(item)
            elif t == "analysis.generated":
                self.analyses.append(item)
        self.turns.sort(key=lambda x: (x["ts"], x["seq"]))
        self._build_cycles()
        self._attribute()

    @classmethod
    def load(cls, home=None, cfg=None, repo=None, now=None):
        cfg = cfg or config.load(home)
        return cls(Wal(home).read(), cfg, repo, now)

    # ---- ciclos ----------------------------------------------------------------------
    def _build_cycles(self):
        by_session = {}
        for kind, items in (("prompt", self.prompts), ("turn", self.turns), ("end", self.ends)):
            for it in items:
                by_session.setdefault(it["sessionId"], []).append((it["ts"], KIND_ORDER[kind], it["seq"], kind, it))
        cycles = []
        for sid, evs in by_session.items():
            cur = None
            for _ts, _, _, kind, it in sorted(evs, key=lambda e: e[:3]):
                if kind == "prompt":
                    cur = {"sessionId": sid, "prompt": it, "turns": [], "end": None}
                    cycles.append(cur)
                elif kind == "turn":
                    if cur is None:
                        cur = {"sessionId": sid, "prompt": None, "turns": [], "end": None}
                        cycles.append(cur)
                    cur["turns"].append(it)
                elif cur is not None:
                    cur["end"] = it
        for c in cycles:
            c["startedAt"] = (c["prompt"] or c["turns"][0])["ts"]
            last = c["end"]["ts"] if c["end"] else (c["turns"][-1]["ts"] if c["turns"] else c["startedAt"])
            c["endedAt"] = last
            if c["end"]:
                c["durationMs"], c["estimated"] = c["end"]["durationMs"], False
            else:
                c["durationMs"], c["estimated"] = int(seconds_between(c["startedAt"], last) * 1000), True
        cycles.sort(key=lambda c: (c["startedAt"], c["sessionId"]))
        self.cycles = cycles

    # ---- atribuição (FR-015): explícita > branch/alias > caminho de spec > rascunho ----
    def _active_attributions(self):
        corrected = {e["corrects"] for e in self.attr_events
                     if e["kind"] == "attribution.corrected" and "corrects" in e}
        return [e for e in self.attr_events if e["seq"] not in corrected]

    @staticmethod
    def _covers(event, turn):
        scope = event.get("scope") or {}
        if "sessionId" in scope and scope["sessionId"] != turn["sessionId"]:
            return False
        if "turns" in scope and turn["msgId"] not in scope["turns"]:
            return False
        if "from" in scope and turn["ts"] < scope["from"]:
            return False
        return not ("to" in scope and turn["ts"] > scope["to"])

    def _attribute(self):
        active = self._active_attributions()
        self.workflow_override = {}
        for e in sorted(active, key=lambda e: e["seq"]):
            if e.get("workflow") and e.get("featureId"):
                self.workflow_override[e["featureId"]] = e["workflow"]
        for t in self.turns:
            t["tags"] = sorted({e["tag"] for e in active if e.get("tag") and self._covers(e, t)})
            t["feature"], t["mode"] = self._turn_feature(t, active)
        for c in self.cycles:  # o turno sem evidência herda a do turno anterior do mesmo ciclo (dentro da janela)
            last = None
            for t in c["turns"]:
                if t["feature"] and t["mode"] not in ("explicit", "corrected"):
                    last = t
                elif last and t["feature"] is None and t["mode"] == "unattributed"                         and self._in_window(last["feature"], t["ts"]):
                    t["feature"], t["mode"] = last["feature"], "inferred"
        self._link_drafts()
        parts = []
        for c in self.cycles:
            parts += self._split_cycle(c)
        self.cycles = parts

    def _split_cycle(self, c):
        """Um ciclo cujos turnos pertencem a features diferentes (ex.: uma sessão longa que atravessa
        branches) vira uma parte por feature; o prompt fica com a primeira parte atribuída a uma feature."""
        if not c["turns"]:
            owner = self._branch_owner((c["prompt"] or {}).get("gitBranch"), c["startedAt"])
            c["feature"], c["mode"] = owner, "inferred" if owner else "unattributed"
            return [c]
        groups = {}
        for t in c["turns"]:
            groups.setdefault(t["feature"], []).append(t)
        if len(groups) == 1:
            c["feature"], c["mode"] = c["turns"][0]["feature"], c["turns"][0]["mode"]
            return [c]
        order = list(groups)
        holder = next((f for f in order if f is not None), order[0])
        parts = []
        for i, fid in enumerate(order):
            turns, last = groups[fid], i == len(order) - 1
            part = dict(c, turns=turns, feature=fid, mode=turns[0]["mode"],
                        prompt=c["prompt"] if fid == holder else None, end=None)
            part["startedAt"] = c["startedAt"] if (fid == holder and i == 0) else turns[0]["ts"]
            part["endedAt"] = c["endedAt"] if last else turns[-1]["ts"]
            part["durationMs"] = int(seconds_between(part["startedAt"], part["endedAt"]) * 1000)
            part["estimated"] = True
            parts.append(part)
        return parts

    def _in_window(self, fid, ts):
        """Features históricas têm janela (commits que a criaram e concluíram); fora dela não valem."""
        w = (self.features.get(fid) or {}).get("window")
        if not w:
            return True
        return (not w.get("from") or ts > w["from"]) and (not w.get("to") or ts <= w["to"])

    def _branch_owner(self, branch, ts):
        owner = branch if branch in self.features else (self.aliases.get(branch) or {}).get("featureId")
        return owner if owner and self._in_window(owner, ts) else None

    def _turn_feature(self, t, active):
        if t["source"] == "analysis-overhead":
            return None, "analysis-overhead"
        covering = [e for e in active if e.get("scope") and self._covers(e, t)]
        if covering:
            e = max(covering, key=lambda e: e["seq"])
            return e.get("featureId"), ("corrected" if e["kind"] == "attribution.corrected" else "explicit")
        owner = self._branch_owner(t.get("gitBranch"), t["ts"])
        if owner:
            return owner, "inferred"
        for tool in t.get("tools", []):
            m = re.match(r"(specs/[^/]+)/", tool.get("path") or "")
            owner = self.aliases[m.group(1)]["featureId"] if m and m.group(1) in self.aliases else None
            if owner and self._in_window(owner, t["ts"]):
                return owner, "inferred"
        return None, "unattributed"

    def _link_drafts(self):
        """Rascunho = turnos sem evidência nos branches principais, por sessão. Só se liga a uma
        feature (não histórica) criada na janela dele (+ folga); senão é exploração sem entrega."""
        main = set(self.cfg["main_branches"])
        by_session = {}
        for t in self.turns:
            if t["feature"] is None and t["mode"] == "unattributed" and (
                    t.get("gitBranch") in main or not t.get("gitBranch")):
                by_session.setdefault(t["sessionId"], []).append(t)
        grace = timedelta(minutes=self.cfg["draft_link_grace_minutes"])
        self.drafts = []
        for sid, turns in sorted(by_session.items()):
            start, end = turns[0]["ts"], turns[-1]["ts"]
            limit = parse_ts(end) + grace
            born = [(f["bornAt"], fid) for fid, f in self.features.items()
                    if f.get("dataClass", "observed") != "historical"
                    and start <= f["bornAt"] and parse_ts(f["bornAt"]) <= limit]
            linked = min(born)[1] if born else None
            self.drafts.append({"sessionId": sid, "start": start, "end": end, "turns": turns, "linked": linked})
            for t in turns:
                t["draft"] = "linked" if linked else "unlinked"
                if linked:
                    t["feature"], t["mode"] = linked, "inferred"

    # ---- consultas -------------------------------------------------------------------
    def feature_ids(self):
        return sorted(self.features, key=lambda f: (self.features[f]["bornAt"], f))

    def resolve(self, name):
        """featureId a partir do id, de um alias (`specs/NNN-x`) ou do nome do diretório de spec."""
        if name in self.features:
            return name
        for alias, item in self.aliases.items():
            if name in (alias, alias.rstrip("/").split("/")[-1]):
                return item["featureId"]
        return None

    def turns_of(self, fid, include_setup=True):
        return [t for t in self.turns
                if t["feature"] == fid and (include_setup or "setup" not in t["tags"])]

    def cycles_of(self, fid):
        return [c for c in self.cycles if c["feature"] == fid]

    def aliases_of(self, fid):
        return sorted(a for a, i in self.aliases.items() if i["featureId"] == fid)

    # ---- situação e classe de custo (FR-018) -----------------------------------------
    def _main(self):
        if self.repo is None:
            return self.cfg["main_branches"][0]
        return next((b for b in self.cfg["main_branches"] if gitinfo.branch_exists(self.repo, b)),
                    self.cfg["main_branches"][0])

    def status(self, fid):
        """entregue (integrada ao principal) | abandonada (sem atividade há N dias e nunca
        integrada) | em andamento. `status.corrected` vence. Calculada, nunca gravada."""
        if fid not in self._status:
            corrections = [e for e in self.status_events if e["featureId"] == fid]
            self._status[fid] = (max(corrections, key=lambda e: e["seq"])["status"]
                                 if corrections else self._computed_status(fid))
        return self._status[fid]

    def _computed_status(self, fid):
        if self.repo is not None:
            main, born = self._main(), self.features[fid]["bornAt"]
            try:
                if gitinfo.is_merged_into(self.repo, fid, main, since=born) or \
                        gitinfo.merge_commit_for_branch(self.repo, main, fid):
                    return "entregue"
            except gitinfo.GitError:
                pass
        turns = self.turns_of(fid)
        last = turns[-1]["ts"] if turns else self.features[fid]["bornAt"]
        if self.now - parse_ts(last) > timedelta(days=self.cfg["abandon_after_days"]):
            return "abandonada"
        return "em andamento"

    def cost_class(self, turn):
        """entregue | abandonada | em andamento | exploração sem entrega | unattributed |
        sobrecarga de análise. `em andamento` fica fora dos agregados por classe."""
        if turn["mode"] == "analysis-overhead":
            return "sobrecarga de análise"
        if turn["feature"]:
            return self.status(turn["feature"])
        return "exploração sem entrega" if turn.get("draft") == "unlinked" else "unattributed"


# ---- backfill do histórico anterior à ferramenta (features 005 e 006) -------------------
def backfill_events(model, repo, cfg):
    """Eventos para importar features sem captura desde o nascimento: `historical` / `partial`.

    A janela de cada feature vem de `history_windows` (commits que a criaram e concluíram). Os turnos
    entram por evidência de caminho (`specs/NNN-*`) ou pelo branch, dentro da janela; o resto fica
    `unattributed`. O trabalho feito fora do Claude Code vira uma lacuna `copilot`. Idempotente."""
    events, notes = [], []
    for fid, w in cfg["history_windows"].items():
        if (model.features.get(fid) or {}).get("dataClass") == "historical":
            notes.append(f"{fid}: já importada")
            continue
        prefix = fid.split("-")[0]
        try:
            start = gitinfo.commit_time(repo, w["startAfterCommit"]) if w.get("startAfterCommit") else None
            end = gitinfo.commit_time(repo, w["endCommit"]) if w.get("endCommit") else None
        except gitinfo.GitError:
            start = end = None
        if w.get("endCommit") and end is None:
            notes.append(f"{fid}: commit {w['endCommit']} não encontrado neste repositório; janela sem limite final")
        window_ok = lambda ts: (not start or ts > start) and (not end or ts <= end)  # noqa: E731
        dirs, candidates = set(), []
        for t in model.turns:
            if t["source"] == "analysis-overhead" or not window_ok(t["ts"]):
                continue
            spec_dirs = {m.group(1) for tool in t.get("tools", [])
                         for m in [re.match(rf"(specs/{re.escape(prefix)}-[^/]+)/", tool.get("path") or "")] if m}
            if t.get("gitBranch") == fid or spec_dirs:
                candidates.append(t)
                dirs |= spec_dirs
        born = start or (candidates[0]["ts"] if candidates else end) or "1970-01-01T00:00:00Z"
        window = {k: v for k, v in (("from", start), ("to", end), ("endCommit", w.get("endCommit"))) if v}
        events.append({"type": "feature.born", "ts": born, "source": "backfill", "data": {
            "featureId": fid, "bornAt": born, "bornSource": "declared", "dataClass": "historical",
            "coverage": "partial", "window": window}})
        for d in sorted(dirs):
            if d not in model.aliases:
                events.append({"type": "feature.alias", "ts": born, "source": "backfill", "data": {
                    "featureId": fid, "alias": d, "source": "path-evidence"}})
        gap_to = candidates[0]["ts"] if candidates else (end or born)
        events.append({"type": "coverage.gap", "ts": born, "source": "backfill", "data": {
            "source": "copilot", "from": born, "to": gap_to, "reason": "copilot", "recovered": False,
            "featureId": fid}})
        notes.append(f"{fid}: {len(candidates)} turnos por evidência de caminho/branch, "
                     f"{len(dirs)} diretório(s) de spec")
    return events, notes
