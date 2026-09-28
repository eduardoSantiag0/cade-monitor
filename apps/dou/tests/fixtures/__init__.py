import json
from pathlib import Path

_FIXTURES_DIR = Path(__file__).parent


def load_fixture(name: str) -> dict:
    with open(_FIXTURES_DIR / name, encoding='utf-8') as f:
        return json.load(f)
