"""Auxiliares de teste: transcrições SINTÉTICAS, repositório Git temporário, --home temporário.

Nunca copie transcrições reais para cá: elas contêm texto de conversa."""
import json
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

FAKE_BOT = "ExemploBot"


def tmp_dir(testcase):
    d = tempfile.TemporaryDirectory()
    testcase.addCleanup(d.cleanup)
    return Path(d.name)


def git(repo, *args, env=None, check=True):
    e = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
             GIT_COMMITTER_EMAIL="t@t", **(env or {}))
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", env=e)
    if check and r.returncode:
        raise RuntimeError(f"git {args} falhou: {r.stderr}")
    return r.stdout.strip()


def make_repo(testcase, files=None):
    """Repositório Git temporário com `main` e um commit inicial."""
    repo = tmp_dir(testcase)
    git(repo, "init", "-q", "-b", "main")
    for rel, content in (files or {"README.md": "x"}).items():
        write_file(repo, rel, content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init", env={"GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z"})
    return repo


def write_file(root, rel, content="x"):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class Transcript:
    """Monta linhas de transcrição no formato do Claude Code, uma linha por bloco de conteúdo."""

    def __init__(self, root, session="sess-1", branch="main", model="claude-opus-5-5",
                 start="2026-09-22T10:00:00", effort="medium"):
        self.root = Path(root)
        self.session, self.branch, self.model, self.effort = session, branch, model, effort
        self.t = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
        self.lines = []
        self.last_uuid = None

    def _ts(self, seconds=5):
        self.t += timedelta(seconds=seconds)
        return self.t.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def _base(self, typ, seconds=5):
        u = str(uuid.uuid4())
        d = {"type": typ, "uuid": u, "timestamp": self._ts(seconds), "sessionId": self.session,
             "gitBranch": self.branch, "cwd": str(self.root), "isSidechain": False}
        return d, u

    def advance(self, minutes):
        self.t += timedelta(minutes=minutes)

    def permission_mode(self, mode="auto"):
        self.lines.append({"type": "permission-mode", "permissionMode": mode, "sessionId": self.session})

    def prompt(self, text="faça algo", skill=None, args=""):
        d, u = self._base("user", 30)
        d["promptId"] = str(uuid.uuid4())
        d["origin"] = {"kind": "human"}
        content = text
        if skill:
            content = f"<command-message>{skill}</command-message>\n<command-name>/{skill}</command-name>"
            if args:
                content += f"\n<command-args>{args}</command-args>"
        d["message"] = {"role": "user", "content": content}
        self.lines.append(d)
        self.last_uuid = u
        return d

    def assistant(self, tools=(), usage=(2, 100, 1000, 200), stop=None, msg_id=None, text=True,
                  model=None, results=True, is_error=()):
        """`tools`: ("Edit", rel, old, new) | ("Write", rel, content) | ("Read", rel) |
        ("Bash", cmd) | ("Skill", nome). Emite uma linha por bloco, todas com o mesmo usage."""
        msg_id = msg_id or "msg_" + uuid.uuid4().hex[:12]
        stop = stop or ("tool_use" if tools else "end_turn")
        blocks, tool_ids = [], []
        if text:
            blocks.append({"type": "text", "text": text if isinstance(text, str) else "resposta"})
        for t in tools:
            tid = "toolu_" + uuid.uuid4().hex[:12]
            tool_ids.append(tid)
            name = t[0]
            if name == "Edit":
                inp = {"file_path": str(self.root / t[1]), "old_string": t[2], "new_string": t[3]}
            elif name == "MultiEdit":
                inp = {"file_path": str(self.root / t[1]), "edits": [{"old_string": o, "new_string": n} for o, n in t[2]]}
            elif name == "Write":
                inp = {"file_path": str(self.root / t[1]), "content": t[2]}
            elif name == "Read":
                inp = {"file_path": t[1] if os.path.isabs(t[1]) else str(self.root / t[1])}
            elif name in ("Bash", "PowerShell"):
                inp = {"command": t[1], "description": "d"}
            elif name == "Skill":
                inp = {"skill": t[1]}
            else:
                inp = {}
            blocks.append({"type": "tool_use", "id": tid, "name": name, "input": inp})
        u_in, u_out, u_cr, u_cc = usage
        use = {"input_tokens": u_in, "output_tokens": u_out, "cache_read_input_tokens": u_cr,
               "cache_creation_input_tokens": u_cc, "output_tokens_details": {"thinking_tokens": 0}}
        last_uuid = None
        for b in blocks:
            d, u = self._base("assistant", 3)
            d["effort"] = self.effort
            d["message"] = {"id": msg_id, "model": model or self.model, "role": "assistant",
                            "content": [b], "stop_reason": stop, "usage": use}
            self.lines.append(d)
            last_uuid = u
        if results:
            for i, tid in enumerate(tool_ids):
                self.tool_result(tid, is_error=i in is_error)
        self.last_uuid = last_uuid
        return msg_id

    def tool_result(self, tool_id, is_error=False, git_op=None):
        d, _ = self._base("user", 2)
        block = {"type": "tool_result", "tool_use_id": tool_id, "content": "saída"}
        if is_error:
            block["is_error"] = True
        d["message"] = {"role": "user", "content": [block]}
        d["toolUseResult"] = {"stdout": "x", "stderr": "", "interrupted": False}
        if git_op:
            d["toolUseResult"]["gitOperation"] = git_op
        self.lines.append(d)

    def turn_duration(self, ms=60000):
        d, _ = self._base("system", 1)
        d.update({"subtype": "turn_duration", "durationMs": ms, "parentUuid": self.last_uuid})
        self.lines.append(d)

    def system(self, subtype):
        d, _ = self._base("system", 1)
        d["subtype"] = subtype
        self.lines.append(d)

    def cost_state(self, models, usd=12.5):
        self.lines.append({
            "type": "cost-state", "sessionId": self.session, "totalCostUSD": usd,
            "totalAPIDuration": 1000, "totalToolDuration": 500, "totalDuration": 5000,
            "totalLinesAdded": 10, "totalLinesRemoved": 2,
            "modelUsage": {m: {"inputTokens": v[0], "outputTokens": v[1], "thinkingTokens": 0,
                               "cacheReadInputTokens": v[2], "cacheCreationInputTokens": v[3],
                               "webSearchRequests": 0, "costUSD": 1.0} for m, v in models.items()}})

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            for line in self.lines:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        return path
