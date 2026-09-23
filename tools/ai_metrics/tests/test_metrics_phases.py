import unittest

from tools.ai_metrics.tests.metrics_base import MetricsBase


class PhaseTests(MetricsBase):
    def test_escritas_que_nao_contam_nao_iniciam_a_implementacao(self):
        t = self.branch_transcript()
        outside = str(self.repo.parent / "fora" / "x.py")
        self.cycle(t, turns=[
            {"tools": [("Write", "specs/007-x/spec.md", "a")], "n": 10},
            {"tools": [("Write", "README.md", "a")], "n": 20},
            {"tools": [("Write", ".specify/memory/x.json", "a")], "n": 30},
            {"tools": [("Write", ".claude/settings.json", "a")], "n": 40},
            {"tools": [("Write", "docs/x.md", "a")], "n": 50},
            {"tools": [("Edit", outside, "a", "b")], "n": 60}])
        self.build(t)
        m, res = self.compute()
        self.assertEqual(m["M-impl-start"]["state"], "unknown")
        self.assertIsNone(res["facts"]["implementationStartedAt"])
        self.assertEqual(m["M-tokens-preimpl"]["value"], m["M-tokens-total"]["value"])
        self.assertEqual(m["M-tokens-impl"]["state"], "unknown")  # nunca 0 quando não medido
        self.assertEqual(m["M-tokens-post"]["state"], "unknown")

    def test_fases_dividem_o_total_sem_partir_turnos(self):
        t = self.branch_transcript()
        self.cycle(t, skill="speckit-specify", turns=[{"tools": [("Write", "specs/007-x/spec.md", "a")], "n": 100}])
        self.cycle(t, turns=[{"tools": [("Write", "apps/x/models.py", "a\nb\nc")], "n": 1000},  # turno da 1ª escrita
                             {"tools": [("Bash", "python manage.py test")], "n": 200}])
        self.cycle(t, turns=[{"tools": [("Edit", "apps/x/models.py", "a", "b")], "n": 50}])  # pós-first-pass
        self.build(t)
        m, res = self.compute()
        self.assertEqual(m["M-tokens-preimpl"]["value"], 100 + 1)  # + turno final do 1º ciclo (end_turn)
        self.assertEqual(m["M-tokens-impl"]["value"], 1000 + 200 + 1)
        self.assertEqual(m["M-tokens-post"]["value"], 50 + 1)
        self.assertEqual(m["M-tokens-total"]["value"],
                         m["M-tokens-preimpl"]["value"] + m["M-tokens-impl"]["value"] + m["M-tokens-post"]["value"])
        self.assertEqual(res["facts"]["implementationStartedAt"], res["turns"][2]["ts"])

    def test_primeira_escrita_de_producao_fica_a_parte(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [("Write", "tests/test_x.py", "a")], "n": 10},
                             {"tools": [("Write", "apps/x/models.py", "a")], "n": 10}])
        self.build(t)
        m, res = self.compute()
        self.assertEqual(m["M-impl-start"]["value"], res["turns"][0]["ts"])
        self.assertEqual(m["M-first-prod-write"]["value"], res["turns"][1]["ts"])
        self.assertNotEqual(m["M-impl-start"]["value"], m["M-first-prod-write"]["value"])

    def test_submetricas_de_pre_implementacao(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [("Read", "apps/a.py")], "n": 50}])                        # outros
        self.cycle(t, skill="grill-me", turns=[{"tools": [("Read", "docs/a.md")], "n": 200}])     # grill
        self.cycle(t, skill="speckit-plan", turns=[{"tools": [("Read", "docs/b.md")], "n": 400}]) # planejamento
        self.cycle(t, skill="speckit-plan", turns=[{"tools": [("Write", "specs/007-x/plan.md", "x")], "n": 800}])  # spec
        self.cycle(t, turns=[{"tools": [("Write", "apps/x/a.py", "x")], "n": 5000}])
        self.build(t)
        m, _ = self.compute()
        self.assertEqual(m["M-pre-other"]["value"], 50 + 1)
        self.assertEqual(m["M-pre-grill"]["value"], 200 + 1)   # +1 do turno final do ciclo, ainda com skill ativa
        self.assertEqual(m["M-pre-planning"]["value"], 400 + 1 + 1)  # 2 ciclos speckit-plan: +1 de cada fim de turno
        self.assertEqual(m["M-pre-spec"]["value"], 800)
        sub = sum(m[f"M-pre-{k}"]["value"] for k in ("spec", "grill", "planning", "other"))
        self.assertEqual(sub, m["M-tokens-preimpl"]["value"])

    def test_tokens_por_tipo_e_total(self):
        t = self.branch_transcript()
        t.prompt()
        t.assistant(usage=(1, 2, 3, 4), stop="end_turn")
        self.build(t)
        m, _ = self.compute()
        self.assertEqual([m[f"M-tokens-{k}"]["value"] for k in ("in", "out", "cacheRead", "cacheCreate")], [1, 2, 3, 4])
        self.assertEqual(m["M-tokens-total"]["value"], 10)
        self.assertTrue(m["M-tokens-total"]["warn"])  # aviso de que o total mede contexto × chamadas


if __name__ == "__main__":
    unittest.main()
