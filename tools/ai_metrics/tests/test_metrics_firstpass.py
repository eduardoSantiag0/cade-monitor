import unittest

from tools.ai_metrics.tests.metrics_base import MetricsBase
from tools.ai_metrics.wal import Wal

TEST = ("Bash", "python manage.py test tests")
WRITE_PROD = ("Write", "apps/x/a.py", "l1\nl2")
EDIT_PROD = ("Edit", "apps/x/a.py", "l1", "l1b\nl1c")
WRITE_TEST = ("Write", "tests/test_a.py", "t")


class FirstPassTests(MetricsBase):
    def test_entrega_estrutural_verificada(self):
        t = self.branch_transcript()
        self.cycle(t, skill="speckit-implement", turns=[{"tools": [WRITE_PROD, TEST]}])
        self.build(t)
        m, res = self.compute()
        self.assertEqual(res["facts"]["firstPassSource"], "verified-green (feature-delivery)")
        self.assertEqual(m["M-cycles-until-fp"]["value"], 1)
        self.assertIsNotNone(m["M-first-pass-at"]["value"])

    def test_primeiro_ciclo_presumido_em_outros_workflows(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [WRITE_PROD, TEST]}])
        self.build(t)
        _, res = self.compute()
        self.assertEqual(res["facts"]["firstPassSource"], "verified-green (assumed)")

    def test_commit_como_proxy(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [WRITE_PROD, ("Bash", "git commit -m x")]}])
        self.build(t)
        _, res = self.compute()
        self.assertEqual(res["facts"]["firstPassSource"], "commit-proxy (assumed)")

    def test_sem_verificacao_verde_nem_commit_e_unknown(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [WRITE_PROD, TEST], "err": (1,)}])
        self.build(t)
        m, res = self.compute()
        self.assertIsNone(res["facts"]["firstPassAt"])
        for mid in ("M-first-pass-at", "M-cycles-until-fp", "M-post-fp-tokens", "M-post-fp-ratio",
                    "M-human-turns-post-fp", "M-reedited-files"):
            self.assertEqual(m[mid]["state"], "unknown", mid)
        self.assertNotIn("M-first-pass-success", m)  # nenhum indicador binário

    def test_faixa_de_tarefas_nao_e_entrega(self):
        t = self.branch_transcript()
        self.cycle(t, skill="speckit-implement", args="T001-T003", turns=[{"tools": [WRITE_PROD, TEST]}])
        self.cycle(t, skill="speckit-implement", turns=[{"tools": [EDIT_PROD, ("Bash", "git commit -m x")]}])
        self.build(t)
        m, res = self.compute()
        self.assertEqual(res["facts"]["firstPassSource"], "commit-proxy (feature-delivery)")
        self.assertEqual(m["M-cycles-until-fp"]["value"], 2)

    def test_correcao_por_evento_sobrepoe(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [WRITE_PROD, TEST]}])
        self.cycle(t, turns=[{"tools": [EDIT_PROD, TEST]}])
        self.build(t)
        second = self.model().cycles_of(self.FID)[1]["prompt"]["uuid"]
        Wal(self.home).append([{"type": "firstPass.corrected", "source": "manual",
                                "data": {"featureId": self.FID, "cycleUuid": second, "reason": "1º foi parcial"}}])
        m, res = self.compute()
        self.assertEqual(res["facts"]["firstPassSource"], "corrected")
        self.assertEqual(m["M-cycles-until-fp"]["value"], 2)
        Wal(self.home).append([{"type": "firstPass.corrected", "source": "manual",
                                "data": {"featureId": self.FID, "cycleUuid": None}}])
        self.assertIsNone(self.compute()[1]["facts"]["firstPassAt"])

    def test_metricas_depois_do_first_pass(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [WRITE_PROD, TEST], "n": 100}])            # first-pass
        self.cycle(t, turns=[{"tools": [EDIT_PROD], "n": 40}])                    # reedita a.py: 1 add extra
        self.cycle(t, turns=[{"tools": [("Write", "apps/x/b.py", "n1\nn2\nn3")], "n": 10}])
        self.build(t)
        m, _ = self.compute()
        total = m["M-tokens-total"]["value"]
        self.assertEqual(m["M-post-fp-tokens"]["value"], 40 + 1 + 10 + 1)
        self.assertAlmostEqual(m["M-post-fp-ratio"]["value"], round(52 / total, 4))
        self.assertEqual(m["M-human-turns-post-fp"]["value"], 2)
        self.assertEqual(m["M-post-fp-churn"]["value"], (2 + 1) + 3)   # EDIT: add 2 del 1; Write b.py: add 3
        self.assertEqual(m["M-reedited-files"]["value"], 1)
        self.assertEqual(m["M-post-fp-ratio"]["unit"], "razão")


class FixCycleTests(MetricsBase):
    def fix(self, *turn_specs):
        t = self.branch_transcript()
        self.cycle(t, turns=list(turn_specs))
        self.build(t)
        return self.compute()[0]["M-fix-cycles"]["value"]

    def test_tdd_vermelho_esperado_nao_conta(self):
        self.assertEqual(self.fix({"tools": [WRITE_TEST]}, {"tools": [TEST], "err": (0,)},
                                  {"tools": [WRITE_PROD]}, {"tools": [TEST]}), 0)

    def test_segundo_vermelho_depois_do_esperado_conta(self):
        self.assertEqual(self.fix({"tools": [WRITE_TEST]}, {"tools": [TEST], "err": (0,)},
                                  {"tools": [TEST], "err": (0,)}, {"tools": [EDIT_PROD]}, {"tools": [TEST]}), 1)

    def test_falha_e_edicao_de_producao_conta(self):
        self.assertEqual(self.fix({"tools": [WRITE_PROD]}, {"tools": [TEST], "err": (0,)},
                                  {"tools": [EDIT_PROD]}, {"tools": [TEST]}), 1)

    def test_teste_com_producao_antes_da_falha_nao_e_excecao(self):
        self.assertEqual(self.fix({"tools": [WRITE_TEST]}, {"tools": [WRITE_PROD]}, {"tools": [TEST], "err": (0,)},
                                  {"tools": [EDIT_PROD]}), 1)

    def test_falha_sem_edicao_nao_conta(self):
        self.assertEqual(self.fix({"tools": [WRITE_PROD]}, {"tools": [TEST], "err": (0,)}), 0)


if __name__ == "__main__":
    unittest.main()
