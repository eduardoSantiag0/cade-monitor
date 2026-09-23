"""FR-050: a ferramenta usa só a biblioteca padrão (nenhuma dependência de runtime nova)."""
import ast
import sys
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


class StdlibOnlyTests(unittest.TestCase):
    def test_todos_os_imports_sao_da_stdlib_ou_do_proprio_pacote(self):
        allowed = set(sys.stdlib_module_names) | {"tools"}
        outsiders = sorted({(p.relative_to(PACKAGE).as_posix(), m) for p in PACKAGE.rglob("*.py")
                            for m in imported_modules(p) if m.split(".")[0] not in allowed})
        self.assertEqual(outsiders, [], "dependência fora da biblioteca padrão")

    def test_o_verificador_enxerga_um_import_de_terceiros(self):
        tmp = PACKAGE / "tests" / "_tmp_import_probe.py"
        tmp.write_text("import pydantic\nfrom django import conf\n", encoding="utf-8")
        try:
            self.assertEqual(sorted(imported_modules(tmp)), ["django", "pydantic"])
        finally:
            tmp.unlink()


if __name__ == "__main__":
    unittest.main()
