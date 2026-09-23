import unittest

from tools.ai_metrics.tests.helpers import git, make_repo, write_file
from tools.ai_metrics.tests.metrics_base import MetricsBase
from tools.ai_metrics.wal import Wal

TASKS = """# Tarefas
- [ ] T001 Criar `apps/x/models.py`
- [ ] T002 Testar em tests/test_x.py
- [ ] T003 Documentar em docs/leia.md
- [ ] T004 Serviço em apps/x/services.py
"""


class SpecMetricsTests(MetricsBase):
    def setUp(self):
        super().setUp()
        self.repo = make_repo(self, {"README.md": "x", ".gitignore": ".ai-metrics/\n"})
        self.pdir = self.projects / __import__("tools.ai_metrics.ingest", fromlist=["slug"]).slug(self.repo)
        git(self.repo, "switch", "-q", "-c", self.FID)

    def commit(self, rel, content="c"):
        write_file(self.repo, rel, content)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", f"add {rel}")

    def alias(self):
        Wal(self.home).append([{"type": "feature.alias", "data": {
            "featureId": self.FID, "alias": "specs/007-x", "source": "path-evidence"}}])

    def test_plan_path_coverage_recall_e_precisao(self):
        self.commit("specs/007-x/tasks.md", TASKS)
        self.commit("apps/x/models.py")            # previsto
        self.commit("tests/test_x.py")             # previsto
        self.commit("apps/x/nao_previsto.py")      # extra
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [("Write", "apps/x/models.py", "a")]}])
        self.build(t)
        self.alias()
        m, _ = self.compute()
        # previstos executáveis: models.py, tests/test_x.py, services.py (docs/ é ignorado) -> 3
        # alterados executáveis no diff: models.py, test_x.py, nao_previsto.py -> 3 ; interseção = 2
        self.assertAlmostEqual(m["M-plan-recall"]["value"], round(2 / 3, 4))
        self.assertAlmostEqual(m["M-plan-precision"]["value"], round(2 / 3, 4))
        self.assertTrue(m["M-plan-recall"]["warn"])

    def test_sem_spec_e_nao_se_aplica_nunca_zero(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [("Write", "apps/x/models.py", "a")]}])
        self.build(t)
        m, _ = self.compute()
        for mid in ("M-plan-recall", "M-plan-precision", "M-spec-changes-turns", "M-spec-changes-tokens"):
            self.assertEqual((m[mid]["state"], m[mid]["value"]), ("na", None), mid)

    def test_spec_sem_tasks_md_e_nao_se_aplica(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [("Write", "apps/x/models.py", "a")]}])
        self.build(t)
        self.alias()
        self.assertEqual(self.compute()[0]["M-plan-recall"]["state"], "na")

    def test_edicoes_de_spec_depois_do_inicio_da_implementacao(self):
        t = self.branch_transcript()
        self.cycle(t, turns=[{"tools": [("Write", "specs/007-x/spec.md", "a")], "n": 100},   # antes: não conta
                             {"tools": [("Write", "apps/x/models.py", "a")], "n": 10},
                             {"tools": [("Edit", "specs/007-x/plan.md", "a", "b")], "n": 30},
                             {"tools": [("Edit", "specs/007-x/tasks.md", "a", "b")], "n": 40}])
        self.build(t)
        self.alias()
        m, _ = self.compute()
        self.assertEqual(m["M-spec-changes-turns"]["value"], 2)
        self.assertEqual(m["M-spec-changes-tokens"]["value"], 70)
        self.assertTrue(m["M-spec-changes-turns"]["warn"])


if __name__ == "__main__":
    unittest.main()
