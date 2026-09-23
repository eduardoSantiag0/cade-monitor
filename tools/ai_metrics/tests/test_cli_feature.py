import os
import unittest
from unittest import mock

from tools.ai_metrics.tests.helpers import FAKE_BOT
from tools.ai_metrics.tests.test_report import ReportBase, TEST
from tools.ai_metrics.wal import Wal


class FeatureCommandTests(ReportBase):
    def setUp(self):
        super().setUp()
        t = self.branch_transcript(session="sX")
        self.cycle(t, turns=[{"tools": [("Write", "apps/x/a.py", "l"), TEST]}])
        self.cycle(t, turns=[{"tools": [("Edit", "apps/x/a.py", "l", "m")]}])
        self.build(t)

    def feat(self, *argv):
        return self.cli("feature", *argv, "--repo", str(self.repo))

    def last(self):
        return Wal(self.home).read()[-1]

    def test_use_grava_atribuicao_e_preserva_o_historico(self):
        before = Wal(self.home).read()
        code, out, _ = self.feat("use", "008-y", "--session", "sX", "--workflow", "grill", "--reason", "teste")
        self.assertEqual(code, 0)
        recs = Wal(self.home).read()
        self.assertEqual(recs[:len(before)], before)
        self.assertEqual([r["type"] for r in recs[len(before):]], ["feature.born", "attribution.set"])
        self.assertEqual(recs[-1]["data"], {"featureId": "008-y", "scope": {"sessionId": "sX"},
                                            "workflow": "grill", "reason": "teste"})
        self.assertEqual(recs[-1]["source"], "manual")
        self.assertEqual(self.cli("verify")[0], 0)

    def test_use_sem_escopo_falha(self):
        code, _, err = self.feat("use", "007-x")
        self.assertEqual(code, 1)
        self.assertIn("escopo", err)

    def test_use_none_declara_unattributed(self):
        self.assertEqual(self.feat("use", "none", "--session", "sX")[0], 0)
        self.assertEqual(self.last()["data"]["featureId"], None)

    def test_correct_reaproveita_o_escopo(self):
        self.feat("use", "008-y", "--session", "sX")
        seq = self.last()["seq"]
        code, _, _ = self.feat("correct", str(seq), "--feature", "007-x")
        self.assertEqual(code, 0)
        rec = self.last()
        self.assertEqual((rec["type"], rec["data"]["corrects"], rec["data"]["scope"]),
                         ("attribution.corrected", seq, {"sessionId": "sX"}))
        self.assertEqual(self.feat("correct", "1", "--feature", "007-x")[0], 1)  # seq 1 não é atribuição

    def test_status_e_first_pass(self):
        self.assertEqual(self.feat("status", "007-x", "entregue", "--reason", "merge por squash")[0], 0)
        self.assertEqual(self.last()["data"], {"featureId": "007-x", "status": "entregue", "reason": "merge por squash"})
        self.assertEqual(self.feat("status", "nao-existe", "entregue")[0], 1)
        model = self.model()
        uuid = model.cycles_of("007-x")[1]["prompt"]["uuid"]
        self.assertEqual(self.feat("first-pass", "007-x", uuid)[0], 0)
        self.assertEqual(self.last()["type"], "firstPass.corrected")
        self.assertEqual(self.feat("first-pass", "007-x", "unknown")[0], 0)
        self.assertEqual(self.feat("first-pass", "007-x", "uuid-de-outro")[0], 1)

    def test_tag_setup(self):
        self.assertEqual(self.feat("tag", "007-x", "--session", "sX", "--tag", "setup")[0], 0)
        self.assertEqual(self.last()["data"]["tag"], "setup")
        self.assertTrue(all("setup" in t["tags"] for t in self.model().turns))

    def test_reason_com_nome_do_bot_e_recusado(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_USERNAME": FAKE_BOT}):
            code, out, err = self.feat("use", "007-x", "--session", "sX", "--reason", f"por causa do {FAKE_BOT}")
        self.assertEqual(code, 1)
        self.assertNotIn(FAKE_BOT.lower(), (out + err).lower())

    def test_recusa_sobre_historico_adulterado(self):
        (self.home / "wal.jsonl").write_bytes((self.home / "wal.jsonl").read_bytes().replace(b'"sidechain":false', b'"sidechain":true', 1))
        self.assertEqual(self.feat("use", "007-x", "--session", "sX")[0], 2)


if __name__ == "__main__":
    unittest.main()
