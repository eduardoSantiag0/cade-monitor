import unittest

from tools.ai_metrics.tests.test_ingest import IngestBase
from tools.ai_metrics.wal import Wal

OPUS = "claude-opus-5-5"
HAIKU = "claude-haiku-4-5-20251001"


class CostValidationTests(IngestBase):
    def session(self, informed, captured=((2, 100, 1000, 200),), **kw):
        t = self.transcript(**kw)
        t.prompt()
        for i, u in enumerate(captured):
            t.assistant(usage=u, stop="end_turn", msg_id=f"m{i}")
        t.cost_state(informed)
        self.save(t)
        return t

    def gaps(self):
        return [r["data"] for r in self.events("coverage.gap")]

    def test_session_cost_so_quando_muda(self):
        self.session({OPUS: (2, 100, 1000, 200)})
        self.run_ingest()
        self.run_ingest()
        cost = self.events("session.cost")
        self.assertEqual(len(cost), 1)
        self.assertEqual(cost[0]["data"]["models"][OPUS],
                         {"in": 2, "out": 100, "cacheRead": 1000, "cacheCreate": 200, "thinking": 0})
        self.assertEqual(cost[0]["data"]["totalMs"], 5000)
        self.assertNotIn("costUSD", self.wal_text())

    def test_totais_iguais_nao_geram_lacuna(self):
        self.session({OPUS: (2, 100, 1000, 200)})
        summary = self.run_ingest()
        self.assertEqual(self.gaps(), [])
        self.assertEqual(summary["divergence"]["sess-1"][OPUS]["cacheRead"], 0.0)
        self.assertEqual(summary["warnings"], [])

    def test_divergencia_pequena_vira_lacuna_sem_aviso(self):
        self.session({OPUS: (2, 100, 1030, 200)})  # 2,9% no cache-read
        summary = self.run_ingest()
        gap = self.gaps()[0]
        self.assertEqual((gap["reason"], gap["recovered"], gap["sessionId"]),
                         ("unlogged-api-calls", False, "sess-1"))
        self.assertAlmostEqual(summary["divergence"]["sess-1"][OPUS]["cacheRead"], 30 / 1030)
        self.assertEqual(summary["warnings"], [])

    def test_divergencia_acima_do_limite_gera_aviso(self):
        self.session({OPUS: (2, 100, 1200, 200)})  # 16,7%
        summary = self.run_ingest()
        self.assertEqual(len(summary["warnings"]), 1)
        self.assertIn("sess-1", summary["warnings"][0])
        self.assertIn("cacheRead", summary["warnings"][0])

    def test_modelo_so_no_cost_state_e_lacuna_nao_turno(self):
        self.session({OPUS: (2, 100, 1000, 200), HAIKU: (900, 20, 0, 0)})
        self.run_ingest()
        self.assertEqual({r["data"]["model"] for r in self.events("turn")}, {OPUS})
        self.assertEqual(len(self.gaps()), 1)

    def test_lacuna_nao_se_repete_e_nova_divergencia_gera_nova(self):
        self.session({OPUS: (2, 100, 1030, 200)})
        self.run_ingest()
        self.run_ingest()
        self.assertEqual(len(self.gaps()), 1)
        self.session({OPUS: (2, 100, 1060, 200)})
        self.run_ingest()
        self.assertEqual(len(self.gaps()), 2)

    def test_campo_ausente_vira_unknown_nao_zero(self):
        t = self.transcript()
        t.prompt()
        t.assistant(stop="end_turn")
        for line in t.lines:
            if line["type"] == "assistant":
                del line["message"]["usage"]["cache_read_input_tokens"]
        self.save(t)
        self.run_ingest()
        usage = self.events("turn")[0]["data"]["usage"]
        self.assertNotIn("cacheRead", usage)
        self.assertEqual(usage["in"], 2)

    def test_historico_continua_integro(self):
        self.session({OPUS: (2, 100, 1030, 200)})
        self.run_ingest()
        self.assertTrue(Wal(self.home).verify()[0])


class UnreadableLinesTests(IngestBase):
    def transcript_file(self):
        t = self.transcript()
        t.prompt()
        t.assistant(stop="end_turn")
        t.turn_duration()
        return t.write(self.pdir / "sess-1.jsonl")

    def corrupt(self, path, where):
        lines = path.read_text(encoding="utf-8").split("\n")
        lines = [ln for ln in lines if ln]
        if where == "middle":
            lines.insert(1, "{isto não é json")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:  # última linha incompleta: o Claude Code ainda está escrevendo
            path.write_text("\n".join(lines) + "\n" + '{"type": "assistant", "mess', encoding="utf-8")

    def gaps(self):
        return [r["data"] for r in self.events("coverage.gap") if r["data"]["reason"] == "unreadable-lines"]

    def test_linha_ilegivel_no_meio_gera_aviso_e_lacuna(self):
        self.corrupt(self.transcript_file(), "middle")
        summary = self.run_ingest()
        (gap,) = self.gaps()
        self.assertEqual((gap["sessionId"], gap["recovered"], gap["lines"]), ("sess-1", False, 1))
        self.assertLessEqual(gap["from"], gap["to"])
        self.assertTrue(any("ilegível" in w and "sess-1.jsonl" in w for w in summary["warnings"]))
        self.assertEqual(len(self.events("turn")), 1)   # o resto do arquivo foi capturado normalmente

    def test_ultima_linha_incompleta_e_normal_e_nao_gera_nada(self):
        self.corrupt(self.transcript_file(), "tail")
        summary = self.run_ingest()
        self.assertEqual(self.gaps(), [])
        self.assertEqual(summary["warnings"], [])

    def test_repetir_a_captura_nao_duplica_a_lacuna(self):
        path = self.transcript_file()
        self.corrupt(path, "middle")
        self.run_ingest()
        self.run_ingest(final=True)
        (self.home / "state.json").unlink()
        self.run_ingest()
        self.assertEqual(len(self.gaps()), 1)
        self.assertTrue(Wal(self.home).verify()[0])

    def test_a_lacuna_torna_a_feature_inelegivel_para_comparacao(self):
        from tools.ai_metrics import metrics
        from tools.ai_metrics.model import Model
        t = self.transcript(branch="007-x")
        t.prompt()
        t.assistant(stop="end_turn")
        t.write(self.pdir / "sess-1.jsonl")
        self.corrupt(self.pdir / "sess-1.jsonl", "middle")
        self.run_ingest(final=True)
        Wal(self.home).append([{"type": "status.corrected", "source": "manual",
                                "data": {"featureId": "007-x", "status": "entregue"}}])
        ok, why = metrics.eligibility(Model.load(self.home, repo=self.repo), "007-x")
        self.assertFalse(ok)
        self.assertIn("lacuna", " ".join(why))


if __name__ == "__main__":
    unittest.main()
