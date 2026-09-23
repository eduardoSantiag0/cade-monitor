import re
import unittest

from tools.ai_metrics import report
from tools.ai_metrics.tests.test_report import CAUSAL, ReportBase, TEST
from tools.ai_metrics.wal import Wal


class CompareBase(ReportBase):
    def mk(self, fid, skills=(), n=1000, session=None, start="2026-09-22T10:00:00", status="entregue"):
        t = self.transcript(branch=fid, session=session or fid, start=start)
        for skill in skills:
            self.cycle(t, skill=skill, turns=[{"tools": [("Read", "docs/a.md")], "n": 10}])
        self.cycle(t, skill="speckit-implement" if "speckit-implement" in skills else None,
                   turns=[{"tools": [("Write", f"apps/{fid[:3]}/a.py", "l1\nl2"), TEST], "n": n}])
        self.save(t)
        return fid, status

    def set_status(self, *pairs):
        Wal(self.home).append([{"type": "status.corrected", "source": "manual", "data": {
            "featureId": f, "status": s}} for f, s in pairs])

    def compare(self):
        model = self.model()
        return report.compare(model, self.repo), model


class ClassificationTests(CompareBase):
    def setUp(self):
        super().setUp()
        pairs = [self.mk("010-a"),
                 self.mk("011-b", ["speckit-specify", "speckit-implement"], start="2026-09-22T11:00:00"),
                 self.mk("012-c", ["grill-me", "speckit-implement"], start="2026-09-22T12:00:00", status="abandonada"),
                 self.mk("013-d", start="2026-09-22T13:00:00", status="em andamento")]
        self.run_ingest(final=True)
        self.set_status(*pairs)

    def test_workflows_por_skills_efetivamente_usadas(self):
        data, _ = self.compare()
        self.assertEqual({r["id"]: r["workflow"] for r in data["rows"]},
                         {"010-a": "direct", "011-b": "speckit", "012-c": "grill+speckit", "013-d": "direct"})

    def test_so_elegiveis_entram_no_agregado_e_o_resto_e_listado(self):
        data, _ = self.compare()
        self.assertEqual({r["id"] for r in data["eligible"]}, {"010-a", "011-b", "012-c"})
        self.assertEqual({(x["id"], x["why"][0]) for x in data["excluded"]}, {("013-d", "situação: em andamento")})

    def test_n_por_workflow_e_classes_separadas(self):
        text = report.render_comparison(*self.compare())
        for wf in ("direct", "speckit", "grill+speckit"):
            self.assertRegex(text, rf"\| {re.escape(wf)} \| 1 \|")
        for klass in ("entregue", "abandonada", "exploração sem entrega", "unattributed"):
            self.assertIn(klass, text)
        self.assertIn("n = 3 features elegíveis", text)

    def test_vieses_e_sem_linguagem_causal(self):
        text = report.render_comparison(*self.compare())
        for bias in ("escolhido pelo desenvolvedor", "n pequeno", "aprendizado", "modelo e esforço"):
            self.assertIn(bias.lower(), text.lower())
        self.assertIsNone(CAUSAL.search(text))
        self.assertNotIn("melhor workflow", text.lower())


class ExclusionTests(CompareBase):
    def test_historicas_e_setup_ficam_fora_dos_agregados(self):
        fid, st = self.mk("010-a")
        setup = self.transcript(branch="main", session="setup", start="2026-09-22T09:00:00")
        self.cycle(setup, turns=[{"n": 7777}])
        self.save(setup)
        self.run_ingest(final=True)
        Wal(self.home).append([
            {"type": "status.corrected", "source": "manual", "data": {"featureId": fid, "status": st}},
            {"type": "feature.born", "source": "backfill", "data": {
                "featureId": "006-h", "bornAt": "2026-09-01T00:00:00Z", "bornSource": "declared",
                "dataClass": "historical", "coverage": "partial"}},
            {"type": "status.corrected", "source": "manual", "data": {"featureId": "006-h", "status": "entregue"}},
            {"type": "attribution.set", "source": "manual", "data": {
                "featureId": fid, "scope": {"sessionId": "setup"}, "tag": "setup"}}])
        data, model = self.compare()
        self.assertEqual([r["id"] for r in data["eligible"]], ["010-a"])
        self.assertIn(("006-h", "feature histórica (dado parcial)"),
                      [(x["id"], x["why"][0]) for x in data["excluded"]])
        row = data["eligible"][0]
        total_feature = sum(t["usage"]["cacheRead"] for t in model.turns_of("010-a", include_setup=False))
        self.assertEqual(row["tokens"], total_feature)          # sem os 7777 tokens da conversa de setup
        self.assertNotEqual(row["tokens"], total_feature + 7777)
        self.assertNotIn("006-h", [r["id"] for r in data["eligible"]])


class UnattributedTests(CompareBase):
    def build_features(self, unattributed_speckit):
        pairs = [self.mk("010-a"), self.mk("011-b", ["speckit-specify", "speckit-implement"], start="2026-09-22T11:00:00")]
        x = self.transcript(branch="main", session="explora", start="2026-09-20T09:00:00")
        if unattributed_speckit:
            self.cycle(x, skill="speckit-specify", turns=[{"n": unattributed_speckit}])
        self.save(x)
        self.run_ingest(final=True)
        self.set_status(*pairs)

    def test_proporcao_de_unattributed_por_workflow_e_comparacao_fraca(self):
        self.build_features(unattributed_speckit=5000)
        data, _ = self.compare()
        prop = data["unattributed_share"]
        self.assertEqual(prop["direct"], 0.0)
        self.assertGreater(prop["speckit"], 0.5)
        self.assertTrue(data["weak"])
        text = report.render_comparison(*self.compare())
        self.assertIn("comparação fraca", text)
        self.assertIn("exploração sem entrega", text)

    def test_sem_unattributed_nao_e_fraca(self):
        self.build_features(unattributed_speckit=0)
        data, _ = self.compare()
        self.assertFalse(data["weak"])
        self.assertNotIn("comparação fraca", report.render_comparison(*self.compare()))


class CompareCommandTests(CompareBase):
    def test_compare_grava_e_report_all_tambem(self):
        pairs = [self.mk("010-a"), self.mk("011-b", ["speckit-implement"], start="2026-09-22T11:00:00")]
        self.run_ingest(final=True)
        self.set_status(*pairs)
        code, out, _ = self.cli("compare", "--stdout", "--repo", str(self.repo))
        self.assertEqual(code, 0)
        self.assertIn("# Comparação entre workflows", out)
        path = self.repo / ".ai-metrics" / "reports" / "_comparacao.md"
        self.assertTrue(path.exists())
        path.unlink()
        self.assertEqual(self.cli("report", "--all", "--repo", str(self.repo))[0], 0)
        self.assertTrue(path.exists())
        (self.repo / ".gitignore").write_text("", encoding="utf-8")
        self.assertEqual(self.cli("compare", "--repo", str(self.repo))[0], 1)  # recusa se não ignorado


if __name__ == "__main__":
    unittest.main()
