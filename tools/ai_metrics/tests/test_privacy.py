"""Varredura de privacidade (SC-004): nada de texto de conversa, comando, conteúdo de arquivo,
valor monetário ou nome do bot no histórico, nos relatórios, na comparação e na análise."""
import os
import re
import unittest
from unittest import mock

from tools.ai_metrics.tests.helpers import FAKE_BOT
from tools.ai_metrics.tests.test_analysis import AnalysisBase
from tools.ai_metrics.tests.test_report import TEST

SECRETS = ("PROMPT-SECRETO-XYZ", "RESPOSTA-SECRETA-XYZ", "SAIDA-SECRETA-XYZ", "CMD-SECRETO-XYZ",
           "CONTEUDO-SECRETO-XYZ", "VELHO-SECRETO-XYZ", "NOVO-SECRETO-XYZ", "ARGUMENTO-SECRETO-XYZ")


class PrivacyScanTests(AnalysisBase):
    def test_varredura_do_historico_dos_relatorios_e_da_analise(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_USERNAME": "@" + FAKE_BOT}):
            t = self.transcript(branch=self.FID, session="privada")
            t.prompt("PROMPT-SECRETO-XYZ")
            t.prompt(skill="speckit-implement", args="ARGUMENTO-SECRETO-XYZ")
            t.assistant(text="RESPOSTA-SECRETA-XYZ", usage=(1, 2, 300, 4), tools=[
                ("Bash", "echo CMD-SECRETO-XYZ && python manage.py test"),
                ("Write", "apps/x/priv.py", "CONTEUDO-SECRETO-XYZ\nl2"),
                ("Edit", "apps/x/priv.py", "VELHO-SECRETO-XYZ", "NOVO-SECRETO-XYZ"), TEST])
            t.assistant(stop="end_turn", usage=(1, 1, 1, 1))
            t.turn_duration()
            t.cost_state({"claude-opus-5-5": (2, 3, 301, 5)}, usd=12.5)
            for line in t.lines:   # resultados de ferramenta também carregam texto
                if line.get("toolUseResult"):
                    line["toolUseResult"]["stdout"] = "SAIDA-SECRETA-XYZ"
                    line["message"]["content"][0]["content"] = "SAIDA-SECRETA-XYZ"
            self.build(t)
            self.respond({"statements": [{"type": "fact", "text": "Há turnos registrados.", "evidence": ["M-turns"]}],
                          "limitations": ["Amostra de uma feature."]})
            self.assertEqual(self.cli("report", "--all", "--repo", str(self.repo))[0], 0)
            with mock.patch.object(__import__("tools.ai_metrics.analysis", fromlist=["x"]), "default_command",
                                   lambda m=None: self.cmd):
                self.assertEqual(self.cli("analyze", self.FID, "--repo", str(self.repo))[0], 0)
            self.assertEqual(self.cli("compare", "--repo", str(self.repo))[0], 0)
            self.assertEqual(self.cli("timeline", "--repo", str(self.repo))[0], 0)

        files = [p for root in (self.home, self.repo / ".ai-metrics") for p in root.rglob("*")
                 if p.is_file() and p.name != "calls.json"]
        names = {p.name for p in files}
        self.assertTrue({"wal.jsonl", "head.json", "007-x.md", "_comparacao.md"} <= names, names)
        money = re.compile(r"usd|\$", re.IGNORECASE)
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for secret in SECRETS:
                self.assertNotIn(secret, text, f"{secret} vazou para {path.name}")
            self.assertNotIn(FAKE_BOT.lower(), text.lower(), f"nome do bot em {path.name}")
            self.assertIsNone(money.search(text), f"valor monetário em {path.name}")
            self.assertNotIn("12.5", text, f"custo em {path.name}")


if __name__ == "__main__":
    unittest.main()
