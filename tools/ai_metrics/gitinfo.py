"""Consultas ao Git via subprocess (só leitura). Sempre UTF-8; falha com mensagem clara."""
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class GitError(Exception):
    pass


def run(repo, *args, check=True):
    try:
        r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"não consegui executar o git: {exc}") from exc
    if check and r.returncode:
        raise GitError(f"git {' '.join(args)} falhou: {r.stderr.strip()}")
    return r.returncode, r.stdout.strip()


def _utc(iso):
    return datetime.fromisoformat(iso).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def branch_exists(repo, branch):
    return run(repo, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False)[0] == 0


def _creation_entry(repo, branch):
    """(sha, iso_utc) da entrada mais antiga do reflog do branch ('Created from ...'), ou None."""
    rc, out = run(repo, "reflog", "show", "--date=iso-strict", "--format=%H%x09%gd%x09%gs",
                  f"refs/heads/{branch}", check=False)
    if rc or not out:
        return None
    sha, gd, subject = out.splitlines()[-1].split("\t", 2)
    m = re.search(r"@\{(.+)\}", gd)
    if not m or not subject.startswith("branch: Created from"):
        return None
    return sha, _utc(m.group(1))


def branch_created_at(repo, branch):
    """Momento (UTC ISO) em que o branch foi criado, segundo o reflog; None se indisponível."""
    entry = _creation_entry(repo, branch)
    return entry[1] if entry else None


def branch_base_sha(repo, branch):
    entry = _creation_entry(repo, branch)
    return entry[0] if entry else None


def moved_from(repo, branch):
    """Branch em que o HEAD estava quando `branch` foi criado (reflog do HEAD), ou None."""
    rc, out = run(repo, "reflog", "show", "--format=%gs", "HEAD", check=False)
    if rc:
        return None
    for line in reversed(out.splitlines()):
        m = re.match(rf"checkout: moving from (\S+) to {re.escape(branch)}$", line)
        if m:
            return m.group(1)
    return None


def _tip_time(repo, ref):
    rc, out = run(repo, "log", "-1", "--format=%cI", ref, check=False)
    return _utc(out) if rc == 0 and out else None


def commit_time(repo, sha):
    return _tip_time(repo, sha)


def is_merged_into(repo, branch, main, since=None):
    """Branch existente integrado a `main`. `since` (ISO UTC) evita confundir um branch
    recém-criado e ainda vazio (que também é ancestral de `main`) com um branch integrado."""
    if not branch_exists(repo, branch):
        return False
    if run(repo, "merge-base", "--is-ancestor", f"refs/heads/{branch}", main, check=False)[0] != 0:
        return False
    tip = _tip_time(repo, f"refs/heads/{branch}")
    return since is None or (tip is not None and tip >= since)


def merge_commit_for_branch(repo, main, branch):
    """Commit de merge em `main` cujo assunto cita o branch (útil com o branch apagado)."""
    rc, out = run(repo, "log", main, "--merges", "--format=%H%x09%s", check=False)
    if rc:
        return None
    for line in out.splitlines():
        sha, _, subject = line.partition("\t")
        if re.search(rf"(?<![\w/-]){re.escape(branch)}(?![\w-])", subject):
            return sha
    return None


def changed_files(repo, branch, main):
    """Arquivos alterados pela feature: branch existente (base do reflog ou merge-base) ou
    commit de merge em `main`. Vazio se não for possível determinar."""
    if branch_exists(repo, branch):
        base = branch_base_sha(repo, branch)
        if not base:
            rc, base = run(repo, "merge-base", main, f"refs/heads/{branch}", check=False)
            if rc:
                return []
        rc, out = run(repo, "diff", "--name-only", f"{base}..refs/heads/{branch}", check=False)
        return out.splitlines() if rc == 0 else []
    merge = merge_commit_for_branch(repo, main, branch)
    if merge:
        rc, out = run(repo, "diff", "--name-only", f"{merge}^1", merge, check=False)
        return out.splitlines() if rc == 0 else []
    return []


def show_file(repo, branch, main, rel):
    """Conteúdo de `rel` na versão do branch (ou de `main` se integrado; ou da árvore de trabalho)."""
    for ref in (f"refs/heads/{branch}", main):
        rc, out = run(repo, "show", f"{ref}:{rel}", check=False)
        if rc == 0:
            return out
    p = Path(repo) / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None


def check_ignored(repo, rel):
    """True se `git check-ignore` confirma que o caminho é ignorado."""
    return run(repo, "check-ignore", "-q", rel, check=False)[0] == 0
