import unittest

from tools.ai_metrics import ingest, report
from tools.ai_metrics.tests.helpers import Transcript
from tools.ai_metrics.tests.metrics_base import tok
from tools.ai_metrics.tests.test_report import ReportBase
from tools.ai_metrics.wal import Wal


class OverheadTests(ReportBase):
    def setUp(self):
        super().setUp()
        self.feature()
        cwd = ingest.analysis_cwd(self.home)
        t = Transcript(cwd, branch=self.FID, session="analise")   # até o gitBranch aponta para a feature
        t.prompt()
        t.assistant(usage=tok(9000), stop="end_turn")
        t.write(self.projects / ingest.slug(cwd) / "analise.jsonl")
        self.run_ingest(final=True)

    def test_classificado_pela_origem(self):
        recs = [r for r in Wal(self.home).read() if r["type"] == "turn"]
        self.assertEqual({r["source"] for r in recs if r["data"]["sessionId"] == "analise"}, {"analysis-overhead"})
        self.assertEqual({r["source"] for r in recs if r["data"]["sessionId"] != "analise"}, {"claude-code"})

    def test_nunca_atribuido_a_feature_nenhuma(self):
        Wal(self.home).append([{"type": "attribution.set", "source": "manual", "data": {
            "featureId": self.FID, "scope": {"sessionId": "analise"}}}])   # nem por declaração explícita
        m = self.model()
        overhead = [t for t in m.turns if t["sessionId"] == "analise"]
        self.assertTrue(overhead and all(t["feature"] is None and t["mode"] == "analysis-overhead" for t in overhead))
        self.assertTrue(all(t["sessionId"] != "analise" for t in m.turns_of(self.FID)))
        self.assertEqual({m.cost_class(t) for t in overhead}, {"sobrecarga de análise"})
        self.assertEqual(m.drafts, [])

    def test_soma_a_parte_no_relatorio_e_na_comparacao(self):
        text, res = self.render()
        self.assertIn("Sobrecarga de análise (fora de qualquer feature)**: 9.000 tokens medidos", text)
        self.assertNotIn("9000", str(res["totals"]))
        self.assertEqual(sum(res["totals"].values()), 653)     # o total da feature não inclui a análise
        data = report.compare(self.model(), self.repo)
        self.assertEqual(data["overhead"], 9000)
        self.assertNotIn("sobrecarga de análise", {k for k in data["classes"]})

    def test_na_linha_do_tempo_fica_a_parte_das_features(self):
        code, out, _ = self.cli("timeline", "--repo", str(self.repo))
        self.assertEqual(code, 0)
        row = next(line for line in out.splitlines() if line.startswith("| 1 |"))
        self.assertNotIn("9.000", row)                                   # a linha da feature não inclui a análise
        self.assertIn("- sobrecarga de análise: 9.000 tokens em 1 turnos", out)   # aparece só como custo à parte


if __name__ == "__main__":
    unittest.main()
