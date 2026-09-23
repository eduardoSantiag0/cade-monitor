import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tools.ai_metrics import cli, ingest
from tools.ai_metrics.tests.test_ingest import IngestBase
from tools.ai_metrics.wal import Wal

ROOT = Path(__file__).resolve().parents[3]


class HookTests(IngestBase):
    def setUp(self):
        super().setUp()
        t = self.transcript()
        t.prompt()
        t.assistant(stop="end_turn")
        self.save(t)

    def hook(self, **kw):
        return ingest.run_hook(self.home, self.repo, self.projects, **kw)

    def test_hook_captura_e_nunca_falha(self):
        self.assertEqual(self.hook(), 0)
        self.assertEqual(len(self.events("turn")), 1)

    def test_falha_vira_errors_log_e_exit_zero(self):
        with mock.patch.object(ingest, "run", side_effect=RuntimeError("boom")):
            self.assertEqual(self.hook(), 0)
        log = (self.home / "errors.log").read_text(encoding="utf-8")
        self.assertIn("boom", log)

    def test_trava_presa_nao_falha_o_turno(self):
        (self.home / "wal.lock").write_text("1")
        real_lock = Wal.lock

        def quick(self_, timeout=5.0):
            return real_lock(self_, timeout=0.2)

        with mock.patch.object(Wal, "lock", quick):
            self.assertEqual(self.hook(), 0)
        self.assertIn("trava", (self.home / "errors.log").read_text(encoding="utf-8"))

    def test_pasta_do_historico_ilegivel_nao_falha(self):
        bad = self.home / "arquivo"
        bad.write_text("x")  # um arquivo no lugar da pasta
        self.assertEqual(ingest.run_hook(bad, self.repo, self.projects), 0)

    def test_proxima_captura_registra_hook_failed(self):
        with mock.patch.object(ingest, "run", side_effect=RuntimeError("boom")):
            self.hook()
        summary = ingest.run(self.home, self.repo, self.projects, final=True)
        gaps = [r["data"] for r in self.events("coverage.gap")]
        self.assertEqual([g["reason"] for g in gaps], ["hook-failed"])
        self.assertTrue(gaps[0]["recovered"])  # a captura recuperou os turnos do intervalo
        self.assertEqual(summary["new"]["coverage.gap"], 1)
        ingest.run(self.home, self.repo, self.projects, final=True)  # não repete
        self.assertEqual(len(self.events("coverage.gap")), 1)

    def test_queda_no_meio_da_gravacao_e_recuperada_pela_captura_seguinte(self):
        self.run_ingest(final=True)
        good = Wal(self.home).read()
        lines = (self.home / "wal.jsonl").read_bytes().split(b"\n")[:-1]
        # queda gravando o último registro: meia linha no arquivo, âncora ainda no penúltimo
        (self.home / "wal.jsonl").write_bytes(b"\n".join(lines[:-1]) + b"\n" + lines[-1][:50])
        (self.home / "head.json").write_text(json.dumps({"seq": good[-2]["seq"], "hash": good[-2]["hash"]}))
        (self.home / "state.json").unlink()
        self.assertEqual(self.hook(), 0)
        after = Wal(self.home).read()
        self.assertEqual([r["hash"] for r in after], [r["hash"] for r in good])   # o evento perdido voltou, sem duplicar
        self.assertTrue(Wal(self.home).verify()[0])

    def test_hook_ignora_stdin_e_nao_imprime(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("sys.stdin", io.StringIO("{lixo")):
            code = cli.main(["--home", str(self.home), "ingest", "--hook",
                             "--projects-dir", str(self.projects), "--repo", str(self.repo)])
        self.assertEqual((code, out.getvalue()), (0, ""))

    def test_duas_capturas_simultaneas_sem_duplicatas(self):
        code = ("import sys\nfrom tools.ai_metrics import ingest\n"
                "sys.exit(ingest.run_hook(sys.argv[1], sys.argv[2], sys.argv[3]))\n")
        procs = [subprocess.Popen([sys.executable, "-c", code, str(self.home), str(self.repo),
                                   str(self.projects)], cwd=ROOT) for _ in range(3)]
        for p in procs:
            self.assertEqual(p.wait(timeout=120), 0)
        self.assertEqual(len(self.events("turn")), 1)
        self.assertTrue(Wal(self.home).verify()[0])


if __name__ == "__main__":
    unittest.main()
