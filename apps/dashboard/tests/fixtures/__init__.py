from pathlib import Path

_FIXTURES_DIR = Path(__file__).parent


def load_fixture(name: str) -> str:
    return (_FIXTURES_DIR / name).read_text(encoding='utf-8')
