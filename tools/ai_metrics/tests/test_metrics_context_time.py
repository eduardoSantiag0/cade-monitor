import unittest

from tools.ai_metrics import metrics, report
from tools.ai_metrics.tests.metrics_base import MetricsBase


class ContextTimeTests(MetricsBase):
    def test_tempo_do_agente_soma_turn_duration(self):
        t = self.branch_transcript()
        self.cycle(t, ms=60000)
        self.cycle(t, ms=30000)
        self.build(t)
        m, res = self.compute()
        self.assertEqual(m["M-agent-seconds"]["value"], 90)
        self.assertIsNone(m["M-agent-seconds"]["note"])
        self.assertFalse(any("tempo humano" in x["label"].lower() for x in m.values()))  # só tempo do agente

    def test_ciclo_sem_turn_duration_e_estimado(self):
        t = self.branch_transcript()
        t.prompt()
        t.assistant(stop="end_turn")
        self.build(t)
        m, _ = self.compute()
        self.assertIn("estimado", m["M-agent-seconds"]["note"])

    def test_intervalo_entre_ciclos_mediana_e_ociosidade(self):
        t = self.branch_transcript()
        for gap_min in (0, 2, 4, 90):  # o último intervalo é ocioso (>= 30 min)
            t.advance(gap_min)
            self.cycle(t)
        self.build(t)
        m, _ = self.compute()
        gaps = m["M-gap-median"]
        self.assertEqual(m["M-idle-gaps"]["value"], 1)
        self.assertIn("leitura, revisão e ausência", gaps["label"])
        self.assertTrue(gaps["warn"])
        self.assertTrue(60 < gaps["value"] < 400)   # mediana entre ~2 e ~4 min de intervalo
        self.assertEqual(gaps["state"], "ok")

    def test_intervalo_sem_pares_e_unknown(self):
        t = self.branch_transcript()
        self.cycle(t)
        self.build(t)
        self.assertEqual(self.compute()[0]["M-gap-median"]["state"], "unknown")

    def test_contexto_pico_media_e_leituras(self):
        t = self.branch_transcript()
        t.prompt()
        t.assistant(tools=[("Read", "apps/a.py"), ("Read", "apps/a.py"), ("Read", "apps/b.py")], usage=(2, 999, 1000, 100))
        t.assistant(usage=(4, 999, 3000, 300), stop="end_turn")
        t.system("compact_boundary")
        t.prompt(skill="clear")
        self.build(t)
        m, _ = self.compute()
        self.assertEqual(m["M-ctx-peak"]["value"], 4 + 3000 + 300)   # entrada + leitura + criação (sem saída)
        self.assertEqual(m["M-ctx-mean"]["value"], round(((2 + 1000 + 100) + (4 + 3000 + 300)) / 2))
        self.assertEqual(m["M-files-read"]["value"], 2)
        self.assertEqual(m["M-reads"]["value"], 3)

    def test_eventos_de_contexto_dentro_do_periodo(self):
        t = self.branch_transcript()
        t.prompt()
        t.assistant(usage=(1, 1, 1, 1))
        t.system("compact_boundary")
        t.assistant(usage=(1, 1, 1, 1), stop="end_turn")
        self.build(t)
        self.assertEqual(self.compute()[0]["M-ctx-events"]["value"], 1)

    def test_volume_de_codigo_e_componentes(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [("Write", "apps/monitoring/a.py", "1\n2\n3"),
                                        ("Edit", "apps/notifications/b.py", "x\ny", "z"),
                                        ("Write", "docs/ignorado.md", "1\n2")]}])
        self.build(t)
        m, res = self.compute()
        self.assertEqual((m["M-lines-added"]["value"], m["M-lines-removed"]["value"]), (4, 2))
        self.assertEqual(m["M-exec-files"]["value"], 2)
        self.assertEqual(res["facts"]["components"], ["monitoring", "notifications"])
        self.assertTrue(m["M-tokens-per-line"]["warn"])


class SessionTimeTests(MetricsBase):
    def test_tempo_de_api_e_ferramenta_por_sessao_fora_das_metricas(self):
        t = self.branch_transcript()
        self.cycle(t)
        t.cost_state({"claude-opus-5-5": (0, 0, 1, 0)})
        self.build(t)
        model = self.model()
        res = metrics.compute(model, self.FID)
        self.assertEqual(res["facts"]["sessionTimes"],
                         [{"sessionId": "sess-1", "apiMs": 1000, "toolMs": 500, "totalMs": 5000}])
        self.assertFalse(any("api" in m["id"].lower() or "tool" in m["id"].lower() for m in res["metrics"]))
        text = report.render_feature(model, self.FID, res)
        self.assertIn("Tempo por sessão (informado pela ferramenta)", text)
        self.assertIn("não é atribuído a ela", text)
        self.assertIn("| `sess-1` | 1 s | 1 s | 5 s |", text)   # 500 ms arredonda para 1 s

    def test_duracao_longa_e_desconhecida(self):
        self.assertEqual(report._dur(3725000), "1 h 2 min 5 s")
        self.assertEqual(report._dur(120000), "2 min")
        self.assertEqual(report._dur(0), "0 s")
        self.assertEqual(report._dur(None), "unknown")

    def test_sem_cost_state_a_secao_nao_aparece(self):
        t = self.branch_transcript()
        self.cycle(t)
        self.build(t)
        model = self.model()
        text = report.render_feature(model, self.FID, metrics.compute(model, self.FID))
        self.assertNotIn("Tempo por sessão", text)


if __name__ == "__main__":
    unittest.main()
