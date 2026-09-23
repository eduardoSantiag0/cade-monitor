import unittest
from datetime import datetime, timezone

from tools.ai_metrics import ingest
from tools.ai_metrics.model import Model
from tools.ai_metrics.tests.helpers import git, make_repo, write_file
from tools.ai_metrics.tests.metrics_base import MetricsBase
from tools.ai_metrics.wal import Wal


def born(fid, at, **extra):
    data = {"featureId": fid, "bornAt": at, "bornSource": "declared", "dataClass": "observed", "coverage": "complete"}
    data.update(extra)
    return {"type": "feature.born", "ts": at, "source": "manual", "data": data}


class DraftTests(MetricsBase):
    def draft_session(self):
        t = self.transcript(branch="main", session="setup", start="2026-09-23T17:32:00")  # turnos ~17:32–17:36
        for _ in range(3):
            self.cycle(t)
        return t

    def model_at(self):
        return self.model()

    def test_vincula_a_feature_criada_na_janela_com_folga(self):
        t = self.draft_session()
        self.build(t)
        end = self.model().turns[-1]["ts"]
        # a feature nasce 28 s depois do fim do rascunho: dentro da folga de 30 min
        Wal(self.home).append([born("007-x", "2026-09-23T17:37:30Z")])
        m = self.model()
        self.assertTrue(end < "2026-09-23T17:37:30Z")
        self.assertEqual({(t["feature"], t["mode"]) for t in m.turns}, {("007-x", "inferred")})
        self.assertEqual(m.drafts[0]["linked"], "007-x")
        self.assertEqual(m.cost_class(m.turns[0]), "em andamento")

    def test_feature_fora_da_janela_deixa_exploracao_sem_entrega(self):
        self.build(self.draft_session())
        Wal(self.home).append([born("007-x", "2026-09-23T19:30:00Z"),      # muito depois
                               born("006-y", "2026-09-23T10:00:00Z")])      # antes do rascunho
        m = self.model()
        self.assertEqual({(t["feature"], t["mode"]) for t in m.turns}, {(None, "unattributed")})
        self.assertIsNone(m.drafts[0]["linked"])
        self.assertEqual({m.cost_class(t) for t in m.turns}, {"exploração sem entrega"})
        self.assertEqual(len(m.turns), 3)   # nunca descartado

    def test_vincula_a_feature_criada_primeiro(self):
        self.build(self.draft_session())
        Wal(self.home).append([born("008-b", "2026-09-23T17:50:00Z"), born("007-a", "2026-09-23T17:40:00Z")])
        self.assertEqual(self.model().drafts[0]["linked"], "007-a")

    def test_historica_nao_recebe_rascunho(self):
        self.build(self.draft_session())
        Wal(self.home).append([born("006-h", "2026-09-23T17:37:00Z", dataClass="historical", coverage="partial")])
        self.assertIsNone(self.model().drafts[0]["linked"])

    def test_turnos_em_feature_nao_formam_rascunho(self):
        t = self.transcript(branch="007-x")
        self.cycle(t)
        self.build(t)
        self.assertEqual(self.model().drafts, [])


class StatusTests(MetricsBase):
    def setUp(self):
        super().setUp()
        self.repo = make_repo(self, {"README.md": "x", ".gitignore": ".ai-metrics/\n"})
        self.pdir = self.projects / ingest.slug(self.repo)
        git(self.repo, "switch", "-q", "-c", self.FID)

    def work(self, start="2026-09-22T10:00:00"):
        t = self.branch_transcript(start=start)
        self.cycle(t)
        self.build(t)

    def commit(self, rel="apps/a.py"):
        write_file(self.repo, rel, "c")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "c")

    def status(self, now="2026-09-25T00:00:00"):
        m = Model.load(self.home, repo=self.repo, now=datetime.fromisoformat(now).replace(tzinfo=timezone.utc))
        return m, m.status(self.FID)

    def test_em_andamento(self):
        self.work()
        self.assertEqual(self.status()[1], "em andamento")

    def test_abandonada_apos_30_dias_e_volta_com_nova_atividade(self):
        self.work()
        self.assertEqual(self.status("2026-11-01T00:00:00")[1], "abandonada")
        self.work(start="2026-10-31T10:00:00")   # nova atividade
        self.assertEqual(self.status("2026-11-01T00:00:00")[1], "em andamento")

    def test_entregue_quando_integrada_ao_principal(self):
        self.work()
        self.commit()
        git(self.repo, "switch", "-q", "main")
        git(self.repo, "merge", "-q", "--ff-only", self.FID)
        m, s = self.status("2026-11-01T00:00:00")
        self.assertEqual(s, "entregue")
        self.assertEqual({m.cost_class(t) for t in m.turns_of(self.FID)}, {"entregue"})

    def test_branch_novo_e_vazio_nao_e_entregue(self):
        self.work()
        git(self.repo, "switch", "-q", "main")
        self.assertEqual(self.status()[1], "em andamento")

    def test_entregue_com_branch_apagado_e_merge_citado(self):
        self.work()
        self.commit()
        git(self.repo, "switch", "-q", "main")
        git(self.repo, "merge", "-q", "--no-ff", self.FID, "-m", f"Merge branch '{self.FID}'")
        git(self.repo, "branch", "-q", "-D", self.FID)
        self.assertEqual(self.status("2026-11-01T00:00:00")[1], "entregue")

    def test_status_corrected_vence(self):
        self.work()
        Wal(self.home).append([{"type": "status.corrected", "source": "manual", "data": {
            "featureId": self.FID, "status": "entregue", "reason": "merge por squash"}}])
        self.assertEqual(self.status("2026-11-01T00:00:00")[1], "entregue")
        Wal(self.home).append([{"type": "status.corrected", "source": "manual", "data": {
            "featureId": self.FID, "status": "em andamento"}}])
        self.assertEqual(self.status("2026-11-01T00:00:00")[1], "em andamento")

    def test_classes_de_custo(self):
        self.work()
        m, _ = self.status("2026-11-01T00:00:00")
        self.assertEqual({m.cost_class(t) for t in m.turns}, {"abandonada"})
        Wal(self.home).append([{"type": "attribution.set", "source": "manual", "data": {
            "featureId": None, "scope": {"sessionId": "sess-1"}}}])
        m, _ = self.status("2026-11-01T00:00:00")
        self.assertEqual({m.cost_class(t) for t in m.turns}, {"unattributed"})


if __name__ == "__main__":
    unittest.main()
