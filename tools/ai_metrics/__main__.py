"""Ponto de entrada: `python -m tools.ai_metrics` ou `python tools/ai_metrics/__main__.py`."""
import sys
from pathlib import Path

# Executado por caminho de arquivo (como no hook): garante que `tools` seja importável.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.ai_metrics.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
