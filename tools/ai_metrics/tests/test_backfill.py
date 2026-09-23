import json
import unittest

from tools.ai_metrics import metrics
from tools.ai_metrics.tests.helpers import git, write_file
from tools.ai_metrics.tests.test_report import ReportBase
from tools.ai_metrics.wal import Wal


class BackfillTests(ReportBase):
    def setUp(self):
        super().setUp()
        git(self.repo, "switch", "-q", "main")
        write_file(self.repo, "apps/a.py", "a")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "005", env={"GIT_COMMITTER_DATE": "2026-09-22T12:00:00Z"})
        self.sha5 = git(self.repo, "rev-parse", "--short", "HEAD")
        write_file(self.repo, "apps/b.py", "b")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "006", env={"GIT_COMMITTER_DATE": "2026-09-22T15:00:00Z"})
        self.sha6 = git(self.repo, "rev-parse", "--short", "HEAD")
        (self.home).mkdir(parents=True, exist_ok=True)
        (self.home / "config.json").write_text(json.dumps({"history_windows": {
            "005-x": {"endCommit": self.sha5},
            "006-y": {"startAfterCommit": self.sha5, "endCommit": self.sha6}}}), encoding="utf-8")

        a = self.transcript(branch="005-x", session="A", start="2026-09-22T10:00:00")
        self.cycle(a, turns=[{"tools": [("Write", "specs/005-x/spec.md", "s")], "n": 100},
                             {"tools": [("Write", "apps/a.py", "l1\nl2"), ("Bash", "python manage.py test")], "n": 200}])
        b = self.transcript(branch="main", session="B", start="2026-09-22T12:30:00")
        self.cycle(b, turns=[{"tools": [("Read", "specs/006-y/plan.md")], "n": 10}])       # evidência de caminho
        self.cycle(b, turns=[{"tools": [("Read", "README.md")], "n": 20}])                 # sem evidência
        c = self.transcript(branch="006-y", session="C", start="2026-09-22T13:00:00")
        self.cycle(c, turns=[{"tools": [("Write", "apps/b.py", "x")], "n": 300}])
        d = self.transcript(branch="006-y", session="D", start="2026-09-22T16:00:00")      # depois da janela
        self.cycle(d, turns=[{"tools": [("Edit", "apps/b.py", "x", "y")], "n": 400}])
        self.build(a, b, c, d)

    def backfill(self):
        return self.cli("backfill", "--repo", str(self.repo))

    def test_eventos_historicos_parciais(self):
        code, out, _ = self.backfill()
        self.assertEqual(code, 0, out)
        recs = Wal(self.home).read()
        born = {r["data"]["featureId"]: r["data"] for r in recs if r["type"] == "feature.born"}
        self.assertEqual({k: (v["dataClass"], v["coverage"]) for k, v in born.items()},
                         {"005-x": ("historical", "partial"), "006-y": ("historical", "partial")})
        self.assertEqual(born["006-y"]["window"]["endCommit"], self.sha6)
        self.assertEqual(born["006-y"]["window"]["from"], "2026-09-22T12:00:00Z")
        aliases = {r["data"]["alias"]: r["data"]["featureId"] for r in recs if r["type"] == "feature.alias"}
        self.assertEqual(aliases, {"specs/005-x": "005-x", "specs/006-y": "006-y"})
        gaps = [r["data"] for r in recs if r["type"] == "coverage.gap"]
        self.assertEqual({(g["reason"], g["featureId"], g["recovered"]) for g in gaps},
                         {("copilot", "005-x", False), ("copilot", "006-y", False)})
        self.assertTrue(Wal(self.home).verify()[0])

    def test_atribuicao_por_evidencia_dentro_da_janela(self):
        self.backfill()
        m = self.model()
        by_session = {}
        for t in m.turns:
            by_session.setdefault(t["sessionId"], set()).add(t["feature"])
        self.assertEqual(by_session["A"], {"005-x"})
        self.assertEqual({t["feature"] for t in m.turns if t["sessionId"] == "B"}, {"006-y", None})
        self.assertEqual(by_session["C"], {"006-y"})
        self.assertEqual(by_session["D"], {None})                       # depois de 95dbc2a: fora da janela
        unattributed_b = [t for t in m.turns if t["sessionId"] == "B" and t["feature"] is None]
        self.assertTrue(unattributed_b and all(t["mode"] == "unattributed" for t in unattributed_b))

    def test_relatorio_historico_diz_minimo_observado_e_pre_impl_unknown(self):
        self.backfill()
        model = self.model()
        res = metrics.compute(model, "006-y", self.repo)
        by = {m["id"]: m for m in res["metrics"]}
        self.assertEqual(by["M-tokens-preimpl"]["state"], "unknown")
        self.assertEqual(by["M-pre-spec"]["state"], "unknown")
        self.assertTrue(by["M-tokens-total"]["lower"])
        self.assertTrue(by["M-turns"]["lower"])
        self.assertEqual(res["facts"]["eligible"], False)
        code, out, _ = self.cli("report", "006-y", "--no-write", "--repo", str(self.repo))
        self.assertIn("mínimo observado", out)
        self.assertIn("Feature histórica", out)
        self.assertIn("historical / partial", out)
        self.assertIn("não — feature histórica", out)
        self.assertNotIn("total consumido", out.lower())

    def test_idempotente(self):
        self.backfill()
        n = len(Wal(self.home).read())
        code, out, _ = self.backfill()
        self.assertEqual(code, 0)
        self.assertIn("já importada", out)
        self.assertEqual(len(Wal(self.home).read()), n)

    def test_linha_do_tempo_mostra_as_historicas(self):
        self.backfill()
        code, out, _ = self.cli("timeline", "--repo", str(self.repo))
        self.assertIn("historical / partial", out)
        self.assertIn("`005-x`", out)
        self.assertIn("unattributed", out)   # custo fora de features aparece à parte

    def test_conversa_de_setup_marcada_fica_fora_das_agregacoes(self):
        self.backfill()
        self.assertEqual(self.cli("feature", "tag", "006-y", "--session", "B", "--tag", "setup",
                                  "--repo", str(self.repo))[0], 0)
        m = self.model()
        self.assertTrue(all("setup" in t["tags"] for t in m.turns if t["sessionId"] == "B"))
        self.assertTrue(all(t["sessionId"] != "B" for t in m.turns_of("006-y", include_setup=False)))
        code, out, _ = self.cli("report", "006-y", "--no-write", "--repo", str(self.repo))
        self.assertIn("conversa marcada `setup`", out)


if __name__ == "__main__":
    unittest.main()
