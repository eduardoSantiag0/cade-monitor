import unittest

from tools.ai_metrics import metrics, report
from tools.ai_metrics.tests.metrics_base import MetricsBase
from tools.ai_metrics.tests.test_report import ReportBase
from tools.ai_metrics.wal import Wal


def gap(**kw):
    data = {"source": "claude-code", "from": "2026-09-22T00:00:00Z", "to": "2026-09-23T00:00:00Z",
            "reason": "hook-failed", "recovered": False}
    data.update(kw)
    return {"type": "coverage.gap", "source": "manual", "data": data}


class LowerBoundTests(ReportBase):
    def setUp(self):
        super().setUp()
        self.feature()

    def metrics_of(self):
        model = self.model()
        return {m["id"]: m for m in metrics.compute(model, self.FID, self.repo)["metrics"]}

    def test_sem_lacuna_nada_e_limite_inferior(self):
        self.assertFalse(any(m["lower"] for m in self.metrics_of().values()))

    def test_lacuna_de_chamadas_nao_registradas_marca_so_tokens(self):
        Wal(self.home).append([gap(reason="unlogged-api-calls", sessionId="sess-1")])
        m = self.metrics_of()
        self.assertTrue(m["M-tokens-total"]["lower"] and m["M-tokens-preimpl"]["lower"])
        self.assertFalse(m["M-turns"]["lower"])
        self.assertEqual(report.fmt(m["M-tokens-total"])[:2], "≥ ")

    def test_lacuna_recuperada_nao_marca_e_aparece_nas_limitacoes(self):
        Wal(self.home).append([gap(recovered=True)])
        self.assertFalse(any(m["lower"] for m in self.metrics_of().values()))
        text, _ = self.render()
        self.assertIn("(recuperada)", text)

    def test_lacuna_que_intersecta_o_periodo_marca_metricas_aditivas(self):
        Wal(self.home).append([gap(reason="hook-failed")])   # intervalo cobre os turnos da feature
        m = self.metrics_of()
        for mid in ("M-turns", "M-cycles", "M-tokens-total", "M-lines-added", "M-agent-seconds"):
            self.assertTrue(m[mid]["lower"], mid)
        self.assertFalse(m["M-ctx-peak"]["lower"])   # não aditiva

    def test_lacuna_fora_do_periodo_nao_marca(self):
        Wal(self.home).append([gap(**{"from": "2020-01-01T00:00:00Z", "to": "2020-01-02T00:00:00Z"})])
        self.assertFalse(any(m["lower"] for m in self.metrics_of().values()))

    def test_texto_de_feature_parcial_diz_minimo_observado(self):
        Wal(self.home).append([gap(reason="unlogged-api-calls", sessionId="sess-1")])
        text, _ = self.render()
        self.assertIn("mínimo observado", text)
        self.assertNotIn("total consumido", text.lower())


class EligibilityTests(MetricsBase):
    def setUp(self):
        super().setUp()
        t = self.branch_transcript()
        self.cycle(t)
        self.build(t)

    def status(self, status):
        Wal(self.home).append([{"type": "status.corrected", "source": "manual",
                                "data": {"featureId": self.FID, "status": status}}])

    def elig(self):
        return metrics.eligibility(self.model(), self.FID)

    def test_observada_completa_e_entregue_e_elegivel(self):
        self.status("entregue")
        self.assertEqual(self.elig(), (True, []))

    def test_em_andamento_nao_e_elegivel(self):
        ok, why = self.elig()
        self.assertFalse(ok)
        self.assertIn("em andamento", " ".join(why))

    def test_historica_ou_parcial_nao_e_elegivel(self):
        self.status("entregue")
        Wal(self.home).append([{"type": "feature.born", "source": "manual", "data": {
            "featureId": self.FID, "bornAt": "2026-09-22T00:00:00Z", "bornSource": "declared",
            "dataClass": "historical", "coverage": "partial"}}])
        ok, why = self.elig()
        self.assertFalse(ok)
        self.assertIn("histórica", " ".join(why))

    def test_lacuna_nao_recuperada_bloqueia_mas_a_sistematica_nao(self):
        self.status("abandonada")
        Wal(self.home).append([gap(reason="unlogged-api-calls", sessionId="sess-1")])
        self.assertTrue(self.elig()[0])
        Wal(self.home).append([gap()])
        ok, why = self.elig()
        self.assertFalse(ok)
        self.assertIn("lacuna", " ".join(why))


class GapCommandTests(ReportBase):
    def test_gap_add_grava_o_evento(self):
        self.feature()
        code, out, _ = self.cli("gap", "add", "--source", "copilot", "--from", "2026-09-19T00:00:00Z",
                                "--to", "2026-09-22T00:00:00Z", "--reason", "copilot", "--feature", "007-x",
                                "--repo", str(self.repo))
        self.assertEqual(code, 0)
        rec = Wal(self.home).read()[-1]
        self.assertEqual(rec["type"], "coverage.gap")
        self.assertEqual(rec["data"], {"source": "copilot", "from": "2026-09-19T00:00:00Z",
                                       "to": "2026-09-22T00:00:00Z", "reason": "copilot",
                                       "recovered": False, "featureId": "007-x"})
        self.assertEqual(rec["source"], "manual")

    def test_gap_add_recusa_motivo_invalido_e_feature_desconhecida(self):
        self.feature()
        base = ["gap", "add", "--source", "x", "--from", "2026-09-19T00:00:00Z", "--to", "2026-09-20T00:00:00Z",
                "--repo", str(self.repo)]
        with self.assertRaises(SystemExit):
            self.cli(*base, "--reason", "qualquer")
        self.assertEqual(self.cli(*base, "--reason", "copilot", "--feature", "nao-existe")[0], 1)


if __name__ == "__main__":
    unittest.main()
