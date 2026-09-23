import contextlib
import io
import os
import re
import time
import unittest
from unittest import mock

from tools.ai_metrics import cli, ingest, metrics, report
from tools.ai_metrics.tests.helpers import FAKE_BOT, git, make_repo
from tools.ai_metrics.tests.metrics_base import MetricsBase
from tools.ai_metrics.wal import Wal

TEST = ("Bash", "python manage.py test tests")
CAUSAL = re.compile(r"causou|reduziu|porque|por causa de|devido a|levou a|resultou em", re.I)


class ReportBase(MetricsBase):
    def setUp(self):
        super().setUp()
        self.repo = make_repo(self, {"README.md": "x", ".gitignore": ".ai-metrics/\n"})
        self.pdir = self.projects / ingest.slug(self.repo)
        git(self.repo, "switch", "-q", "-c", self.FID)

    def feature(self):
        t = self.branch_transcript()
        t.permission_mode("auto")
        self.cycle(t, skill="speckit-specify", turns=[{"tools": [("Write", "specs/007-x/spec.md", "a")], "n": 100}])
        self.cycle(t, skill="speckit-implement", turns=[{"tools": [("Write", "apps/x/a.py", "l1\nl2"), TEST], "n": 500}])
        self.cycle(t, turns=[{"tools": [("Edit", "apps/x/a.py", "l1", "l3")], "n": 50}])
        self.build(t)

    def render(self):
        model = self.model()
        res = metrics.compute(model, self.FID, self.repo)
        return report.render_feature(model, self.FID, res, position=(1, 1)), res

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--home", str(self.home), *argv])
        return code, out.getvalue(), err.getvalue()


class RenderTests(ReportBase):
    def test_secoes_na_ordem_e_n_visivel(self):
        self.feature()
        text, _ = self.render()
        pos = [text.index(h) for h in ("## Fatos", "## Métricas", "## Análise", "## Evidências", "## Limitações")]
        self.assertEqual(pos, sorted(pos))
        self.assertIn("n = 1 feature", text)

    def test_campos_exigidos(self):
        self.feature()
        text, _ = self.render()
        for needle in ("**Workflow**: speckit", "**Modelo(s)**: claude-opus-5-5", "**Esforço**: medium",
                       "**Modo de permissão**: auto", "Tokens de entrada", "Tokens de saída", "leitura de cache",
                       "criação de cache", "Tokens medidos (soma capturada)", "Pré-Implementação", "Ciclos até o first-pass",
                       "Ciclos de correção", "Turnos humanos após o first-pass", "Post-First-Pass Churn",
                       "Linhas executáveis escritas", "Arquivos executáveis alterados", "Arquivos distintos lidos",
                       "**Componentes afetados**: x", "Ordem cronológica**: 1 de 1"):
            self.assertIn(needle, text)

    def test_avisos_e_secundarias(self):
        self.feature()
        text, _ = self.render()
        self.assertIn("mede contexto × número de chamadas", text)
        self.assertIn("(secundária)", text)
        self.assertIn("refatoração legítima", text)

    def test_frases_descritivas_sem_linguagem_causal(self):
        self.feature()
        text, res = self.render()
        self.assertIsNone(CAUSAL.search(text))
        self.assertTrue(all(not CAUSAL.search(s) for s in report.sentences(res)))
        self.assertIn("tokens medidos", text)

    def test_unknown_e_nao_se_aplica_nunca_zero(self):
        t = self.branch_transcript()
        self.cycle(t)
        self.build(t)
        text, _ = self.render()
        self.assertIn("| unknown |", text.replace("unknown (nenhuma escrita em artefato executável)", "unknown"))
        self.assertIn("não se aplica (feature sem spec)", text)
        self.assertIn("O first-pass é unknown", text)

    def test_limitacoes_listam_lacunas(self):
        t = self.branch_transcript()
        self.cycle(t)
        t.cost_state({"claude-opus-5-5": (0, 0, 9999, 0)})
        self.build(t)
        text, _ = self.render()
        self.assertIn("Lacuna `unlogged-api-calls`", text)
        self.assertIn("mínimos observados", text)


class WriteTests(ReportBase):
    def test_grava_e_sobrescreve(self):
        self.feature()
        text, _ = self.render()
        path = report.write_report(self.repo, self.FID, text)
        self.assertEqual(path, self.repo / ".ai-metrics" / "reports" / "007-x.md")
        report.write_report(self.repo, self.FID, "novo")
        self.assertEqual(path.read_text(encoding="utf-8"), "novo")
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")  # nada versionável

    def test_recusa_se_nao_ignorado(self):
        (self.repo / ".gitignore").write_text("", encoding="utf-8")
        with self.assertRaises(report.ReportError) as cm:
            report.write_report(self.repo, self.FID, "x")
        self.assertIn(".gitignore", str(cm.exception))
        self.assertFalse((self.repo / ".ai-metrics").exists())

    def test_recusa_o_nome_do_bot_sem_repeti_lo(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_USERNAME": FAKE_BOT}):
            with self.assertRaises(report.ReportError) as cm:
                report.write_report(self.repo, self.FID, f"relatório de {FAKE_BOT.lower()}")
        self.assertNotIn(FAKE_BOT.lower(), str(cm.exception).lower())
        self.assertFalse((self.repo / ".ai-metrics").exists())


class CliReportTests(ReportBase):
    def test_report_stdout_e_arquivo(self):
        self.feature()
        code, out, _ = self.cli("report", self.FID, "--stdout", "--repo", str(self.repo))
        self.assertEqual(code, 0)
        self.assertIn("# Relatório: 007-x", out)
        self.assertTrue((self.repo / ".ai-metrics" / "reports" / "007-x.md").exists())

    def test_no_write_nao_grava(self):
        self.feature()
        code, out, _ = self.cli("report", self.FID, "--no-write", "--repo", str(self.repo))
        self.assertEqual(code, 0)
        self.assertFalse((self.repo / ".ai-metrics").exists())

    def test_all_e_timeline(self):
        self.feature()
        self.assertEqual(self.cli("report", "--all", "--repo", str(self.repo))[0], 0)
        code, out, _ = self.cli("timeline", "--repo", str(self.repo))
        self.assertEqual(code, 0)
        self.assertIn("`007-x`", out)
        self.assertIn("observed / complete", out)

    def test_feature_desconhecida(self):
        self.feature()
        code, _, err = self.cli("report", "nao-existe", "--repo", str(self.repo))
        self.assertEqual(code, 1)
        self.assertIn("007-x", err)

    def test_historico_adulterado_recusa_relatorio(self):
        self.feature()
        raw = (self.home / "wal.jsonl").read_bytes().replace(b'"turns"', b'"turnz"', 1)
        recs = (self.home / "wal.jsonl").read_bytes()
        (self.home / "wal.jsonl").write_bytes(recs.replace(b'"sidechain":false', b'"sidechain":true', 1))
        code, out, err = self.cli("report", self.FID, "--repo", str(self.repo))
        self.assertEqual(code, 2)
        self.assertIn("integridade", err)
        self.assertFalse((self.repo / ".ai-metrics").exists())


class PerformanceTests(ReportBase):
    def test_500_turnos_em_menos_de_10_segundos(self):
        t = self.branch_transcript()
        for _ in range(100):
            self.cycle(t, turns=[{"tools": [("Edit", "apps/x/a.py", "a", "b"), TEST], "n": 100}] * 4)
        self.build(t)
        start = time.monotonic()
        code, _, _ = self.cli("report", self.FID, "--repo", str(self.repo))
        self.assertEqual(code, 0)
        self.assertLess(time.monotonic() - start, 10)
        self.assertGreaterEqual(len(Wal(self.home).read()), 500)


if __name__ == "__main__":
    unittest.main()
