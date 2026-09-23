"""Configuração, caminhos-padrão e a guarda do nome do bot (Princípio V da constituição)."""
import fnmatch
import json
import os
import re
from pathlib import Path

DEFAULT_HOME = Path.home() / ".cade-metrics"
REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULTS = Path(__file__).with_name("config.default.json")


class ConfigError(Exception):
    """Configuração inválida (mensagem já em português, pronta para exibir)."""


def load(home=None):
    """Padrões versionados + sobrescrita opcional em <home>/config.json (mescla por chave)."""
    cfg = json.loads(_DEFAULTS.read_text(encoding="utf-8"))
    over = Path(home or DEFAULT_HOME) / "config.json"
    if over.exists():
        try:
            extra = json.loads(over.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ConfigError(f"{over} não é um JSON válido: {exc}") from exc
        for key, value in extra.items():
            if key not in cfg:
                print(f"aviso: chave de configuração desconhecida ignorada: {key}")
                continue
            cfg[key] = value
    try:
        for item in cfg["verification_commands"]:
            re.compile(item["pattern"])
        for pattern in cfg["git_operations"].values():
            re.compile(pattern)
    except re.error as exc:
        raise ConfigError(f"expressão regular inválida na configuração: {exc}") from exc
    return cfg


def match_any(path, globs):
    """Casa um caminho relativo (com `/`) contra globs. `*` já cobre `/` no fnmatch, então
    `apps/**` casa qualquer coisa abaixo; `**/x` também casa `x` na raiz."""
    path = str(path).replace("\\", "/")
    for glob in globs:
        if fnmatch.fnmatchcase(path, glob):
            return True
        if glob.startswith("**/") and fnmatch.fnmatchcase(path, glob[3:]):
            return True
    return False


def is_executable(path, cfg):
    """Artefato executável = casa `executable_paths` e não casa `ignore_paths` (ignorar vence)."""
    return match_any(path, cfg["executable_paths"]) and not match_any(path, cfg["ignore_paths"])


def _bot_name(root):
    value = os.environ.get("TELEGRAM_BOT_USERNAME")
    if not value:
        env = Path(root) / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("TELEGRAM_BOT_USERNAME="):
                    value = line.split("=", 1)[1]
    value = (value or "").strip().strip("\"'").lstrip("@").lower()
    return value if len(value) >= 3 else ""


def contains_bot_name(text, root=REPO_ROOT):
    """True se o texto contém o nome real do bot. O valor nunca é impresso nem gravado."""
    name = _bot_name(root)
    return bool(name) and name in text.lower()
