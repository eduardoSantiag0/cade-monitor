import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tools.ai_metrics import config
from tools.ai_metrics.tests.helpers import FAKE_BOT, tmp_dir
from tools.ai_metrics.wal import GENESIS, Wal, WalError

ROOT = Path(__file__).resolve().parents[3]


def ev(n=1, typ="turn"):
    return [{"type": typ, "ts": f"2026-09-22T10:00:0{i}.000Z", "data": {"i": i}} for i in range(n)]


class WalTests(unittest.TestCase):
    def setUp(self):
        self.home = tmp_dir(self)
        self.wal = Wal(self.home)

    def test_append_encadeia_seq_prev_hash(self):
        recs = self.wal.append(ev(3))
        self.assertEqual([r["seq"] for r in recs], [1, 2, 3])
        self.assertEqual(recs[0]["prev"], GENESIS)
        self.assertEqual(recs[1]["prev"], recs[0]["hash"])
        self.assertEqual(self.wal.verify()[0], True)
        self.assertEqual(json.loads((self.home / "head.json").read_text())["seq"], 3)

    def test_verify_detecta_edicao_de_um_byte(self):
        self.wal.append(ev(3))
        raw = (self.home / "wal.jsonl").read_bytes().replace(b'"i":1', b'"i":9')
        (self.home / "wal.jsonl").write_bytes(raw)
        ok, msg, seq = self.wal.verify()
        self.assertFalse(ok)
        self.assertEqual(seq, 2)

    def test_verify_detecta_remocao_no_meio_e_reordenacao(self):
        self.wal.append(ev(4))
        lines = (self.home / "wal.jsonl").read_text().splitlines()
        (self.home / "wal.jsonl").write_text("\n".join([lines[0], lines[2], lines[3]]) + "\n")
        self.assertEqual(self.wal.verify()[2], 2)
        (self.home / "wal.jsonl").write_text("\n".join([lines[0], lines[2], lines[1], lines[3]]) + "\n")
        self.assertFalse(self.wal.verify()[0])

    def test_verify_detecta_truncamento_do_final_pela_ancora(self):
        self.wal.append(ev(4))
        lines = (self.home / "wal.jsonl").read_text().splitlines()
        (self.home / "wal.jsonl").write_text("\n".join(lines[:2]) + "\n")
        ok, msg, seq = self.wal.verify()
        self.assertFalse(ok)
        self.assertEqual(seq, 3)

    def test_ancora_uma_posicao_atras_e_reparada(self):
        self.wal.append(ev(2))
        recs = self.wal.read()
        (self.home / "head.json").write_text(json.dumps({"seq": 1, "hash": recs[0]["hash"]}))
        ok, msg, _ = self.wal.verify()
        self.assertTrue(ok, msg)
        self.assertEqual(json.loads((self.home / "head.json").read_text())["seq"], 2)

    def torn(self, extra=b""):
        """Estado real de uma queda no meio da gravação do registro seq 3: a âncora ainda aponta
        para o seq 2 e o arquivo termina numa meia linha (sem quebra de linha)."""
        self.wal.append(ev(3))
        recs = self.wal.read()
        lines = (self.home / "wal.jsonl").read_bytes().split(b"\n")[:3]
        (self.home / "wal.jsonl").write_bytes(b"\n".join(lines[:2]) + b"\n" + lines[2][:40] + extra)
        (self.home / "head.json").write_text(json.dumps({"seq": recs[1]["seq"], "hash": recs[1]["hash"]}))
        return recs

    def test_cauda_interrompida_e_descartada_e_o_proximo_append_recria_o_seq_3(self):
        recs = self.torn()
        ok, msg, _ = self.wal.verify()
        self.assertTrue(ok, msg)
        self.assertIn("2 registros íntegros", msg)
        self.assertIn("última linha interrompida reparada", msg)
        self.assertTrue((self.home / "wal.jsonl").read_bytes().endswith(b"\n"))
        self.assertEqual(json.loads((self.home / "head.json").read_text())["seq"], 2)   # a âncora nunca foi mexida
        (again,) = self.wal.append([{"type": "turn", "ts": recs[2]["ts"], "data": {"i": 2}}])
        self.assertEqual((again["seq"], again["prev"]), (3, recs[1]["hash"]))
        self.assertTrue(self.wal.verify()[0])

    def test_registro_completo_sem_quebra_de_linha_so_ganha_o_newline(self):
        self.wal.append(ev(2))
        raw = (self.home / "wal.jsonl").read_bytes()
        (self.home / "wal.jsonl").write_bytes(raw.rstrip(b"\n"))   # âncora aponta para o seq 2, que está completo
        ok, msg, _ = self.wal.verify()
        self.assertTrue(ok, msg)
        self.assertEqual(len(self.wal.read()), 2)

    def test_cauda_truncada_que_a_ancora_conhece_nao_e_reparada(self):
        self.wal.append(ev(3))
        cut = (self.home / "wal.jsonl").read_bytes().rstrip(b"\n")[:-30]   # a âncora ainda diz seq 3
        (self.home / "wal.jsonl").write_bytes(cut)
        ok, msg, seq = self.wal.verify()
        self.assertFalse(ok)
        self.assertEqual(seq, 3)
        self.assertEqual((self.home / "wal.jsonl").read_bytes(), cut)   # nada foi alterado

    def test_edicao_no_meio_de_arquivo_terminado_em_newline_continua_falhando(self):
        self.wal.append(ev(3))
        raw = (self.home / "wal.jsonl").read_bytes().replace(b'"i":1', b'"i":8')
        (self.home / "wal.jsonl").write_bytes(raw)
        self.assertFalse(self.wal.verify()[0])

    def test_append_recusa_historico_adulterado(self):
        self.wal.append(ev(2))
        raw = (self.home / "wal.jsonl").read_bytes().replace(b'"i":0', b'"i":7')
        (self.home / "wal.jsonl").write_bytes(raw)
        with self.assertRaises(WalError) as cm:
            self.wal.append(ev(1))
        self.assertTrue(cm.exception.integrity)

    def test_trava_velha_e_removida(self):
        self.home.mkdir(exist_ok=True)
        lock = self.home / "wal.lock"
        lock.write_text("999")
        old = lock.stat().st_mtime - 3600
        os.utime(lock, (old, old))
        self.assertEqual(len(self.wal.append(ev(1))), 1)

    def test_trava_presa_recente_estoura_timeout(self):
        (self.home / "wal.lock").write_text("999")
        with self.assertRaises(WalError):
            with self.wal.lock(timeout=0.2):
                pass

    def test_anexadores_concorrentes_nao_duplicam_seq(self):
        code = (
            "import sys; from tools.ai_metrics.wal import Wal\n"
            "w = Wal(sys.argv[1])\n"
            "for i in range(15): w.append([{'type':'turn','data':{'p':sys.argv[2],'i':i}}])\n"
        )
        procs = [subprocess.Popen([sys.executable, "-c", code, str(self.home), str(p)], cwd=ROOT)
                 for p in range(3)]
        for p in procs:
            self.assertEqual(p.wait(timeout=120), 0)
        recs = self.wal.read()
        self.assertEqual([r["seq"] for r in recs], list(range(1, 46)))
        self.assertTrue(self.wal.verify()[0])

    def test_recusa_campos_monetarios(self):
        for bad in ({"totalCostUSD": 1}, {"m": {"costUSD": 2}}):
            with self.assertRaises(WalError):
                self.wal.append([{"type": "session.cost", "data": bad}])
        self.assertEqual(self.wal.read(), [])

    def test_recusa_nome_do_bot(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_USERNAME": "@" + FAKE_BOT}):
            with self.assertRaises(WalError) as cm:
                self.wal.append([{"type": "turn", "data": {"path": "docs/exemplobot/x.py"}}])
            self.assertNotIn(FAKE_BOT.lower(), str(cm.exception).lower())
        self.assertEqual(self.wal.read(), [])

    def test_guarda_do_bot_ignora_valor_curto_e_ausente(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_USERNAME": "ab"}):
            self.assertFalse(config.contains_bot_name("ab ab ab"))
        env = {k: v for k, v in os.environ.items() if k != "TELEGRAM_BOT_USERNAME"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(config.contains_bot_name("qualquer", root=tmp_dir(self)))


if __name__ == "__main__":
    unittest.main()
