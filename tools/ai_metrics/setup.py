"""Setup local, uma única vez: instala o hook `Stop` em `.claude/settings.local.json`
(arquivo local, não versionado) e prepara a pasta do histórico (contracts/cli.md)."""
import json
import shutil
import sys
from pathlib import Path

from tools.ai_metrics import config, gitinfo, ingest

MAIN = Path(__file__).with_name("__main__.py")
REPORT_PROBE = ".ai-metrics/reports/_probe.md"


class SetupError(Exception):
    pass


def hook_command():
    """Caminhos absolutos (com `/`, que funcionam no bash, no cmd e no Windows em geral): o hook não
    depende do diretório de trabalho de quem o executa."""
    return f'"{Path(sys.executable).as_posix()}" "{MAIN.as_posix()}" ingest --hook'


def _is_ours(command):
    return "ai_metrics" in command and "ingest --hook" in command


def settings_path(repo):
    return Path(repo) / ".claude" / "settings.local.json"


def _load(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SetupError(f"{path} não é um JSON válido ({exc}); nada foi alterado") from exc
    if not isinstance(data, dict):
        raise SetupError(f"{path} não contém um objeto JSON; nada foi alterado")
    return data


def _ours(data):
    """[(grupo, hook)] das entradas da ferramenta dentro de hooks.Stop."""
    return [(g, h) for g in data.get("hooks", {}).get("Stop", []) if isinstance(g, dict)
            for h in g.get("hooks", []) if isinstance(h, dict) and _is_ours(h.get("command", ""))]


def plan_install(data):
    """Aplica a instalação em `data` (mescla só hooks.Stop). Devolve True se algo mudou."""
    cmd, mine = hook_command(), _ours(data)
    if mine:
        changed = False
        for _, h in mine:
            if h.get("command") != cmd:
                h["command"], changed = cmd, True
        return changed
    data.setdefault("hooks", {}).setdefault("Stop", []).append(
        {"hooks": [{"type": "command", "command": cmd}]})
    return True


def plan_remove(data):
    mine = _ours(data)
    for group, hook in mine:
        group["hooks"].remove(hook)
    stop = [g for g in data.get("hooks", {}).get("Stop", []) if g.get("hooks")]
    if "hooks" in data and "Stop" in data["hooks"]:
        if stop:
            data["hooks"]["Stop"] = stop
        else:
            del data["hooks"]["Stop"]
        if not data["hooks"]:
            del data["hooks"]
    return bool(mine)


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(home, repo, projects_dir=None, dry_run=False, remove=False, check=False, out=print):
    """Devolve o código de saída (0 ok, 1 erro ou `--check` falhando)."""
    home, repo = Path(home or config.DEFAULT_HOME), Path(repo)
    path = settings_path(repo)
    try:
        data = _load(path)
    except SetupError as exc:
        out(f"erro: {exc}")
        return 1

    if check:
        installed = bool(_ours(data))
        out(f"hook Stop: {'instalado' if installed else 'NÃO instalado'} ({path})")
        out(f"pasta do histórico: {'existe' if home.is_dir() else 'NÃO existe'} ({home})")
        return 0 if installed and home.is_dir() else 1

    if remove:
        changed = plan_remove(data)
        if changed and not dry_run:
            _write(path, data)
        out(("Hook removido" if changed else "Nenhum hook da ferramenta para remover")
            + f" ({path}). O histórico em {home} foi mantido.")
        return 0

    changed = plan_install(data)
    if dry_run:
        out(f"[dry-run] {'mudaria' if changed else 'não mudaria'} {path}:")
        out("hooks.Stop = " + json.dumps(data.get("hooks", {}).get("Stop", []), indent=2, ensure_ascii=False))
        out(f"[dry-run] criaria a pasta {home}" if not home.is_dir() else f"[dry-run] pasta {home} já existe")
        return 0

    home.mkdir(parents=True, exist_ok=True)
    if changed:
        _write(path, data)
        out(f"Hook Stop instalado em {path}")
    else:
        out(f"Hook Stop já instalado em {path}")
    if not gitinfo.check_ignored(repo, REPORT_PROBE):
        out("AVISO: .ai-metrics/ não está ignorado pelo Git. Adicione `.ai-metrics/` ao .gitignore; "
            "sem isso o comando `report` recusa gravar.")
    try:
        summary = ingest.run(home, repo, projects_dir)
        out(ingest.summary_text(summary))
    except Exception as exc:  # o setup não deve falhar por causa da primeira captura
        out(f"AVISO: a primeira captura falhou ({exc}); rode `ingest` depois.")
    out("Pronto. Fluxo normal: git switch -c <feature> -> trabalhar -> captura automática.")
    return 0
