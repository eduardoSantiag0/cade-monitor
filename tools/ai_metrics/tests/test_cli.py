import contextlib
import io
import unittest

from tools.ai_metrics import cli
from tools.ai_metrics.tests.helpers import tmp_dir
from tools.ai_metrics.wal import Wal


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class CliTests(unittest.TestCase):
    def test_verify_ok_e_falha(self):
        home = tmp_dir(self)
        Wal(home).append([{"type": "turn", "data": {"i": 1}}, {"type": "turn", "data": {"i": 2}}])
        code, out = run("--home", str(home), "verify")
        self.assertEqual(code, 0)
        self.assertIn("OK", out)
        raw = (home / "wal.jsonl").read_bytes().replace(b'"i":1', b'"i":5')
        (home / "wal.jsonl").write_bytes(raw)
        code, out = run("--home", str(home), "verify")
        self.assertEqual(code, 2)
        self.assertIn("seq 1", out)

    def test_help_em_portugues(self):
        with self.assertRaises(SystemExit) as cm:
            run("--help")
        self.assertEqual(cm.exception.code, 0)

    def test_sem_comando_sai_com_1(self):
        self.assertEqual(run()[0], 1)


if __name__ == "__main__":
    unittest.main()
