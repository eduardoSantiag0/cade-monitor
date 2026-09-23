import json
import sys
import unittest
from pathlib import Path

from tools.ai_metrics import analysis
from tools.ai_metrics.tests.test_report import ReportBase
from tools.ai_metrics.wal import Wal

FAKE = '''import json, os, sys
resp, calls = sys.argv[1], sys.argv[2]
open(calls, "w", encoding="utf-8").write(json.dumps({"argv": sys.argv[3:], "cwd": os.getcwd(),
                                                     "stdin": sys.stdin.read()}))
if os.environ.get("FAKE_FAIL"):
    sys.exit(3)
print(json.dumps({"result": open(resp, encoding="utf-8").read(), "is_error": False, "total_cost_usd": 0.5,
                  "modelUsage": {"claude-sonnet-5": {"costUSD": 0.5}}}))
'''


class AnalysisBase(ReportBase):
    def setUp(self):
        super().setUp()
        t = self.branch_transcript()
        t.prompt("SEGREDO-DO-PROMPT: nunca deve ir para a análise")
        t.assistant(tools=[("Write", "apps/x/a.py", "l1\nl2"), ("Bash", "python manage.py test")],
                    usage=(0, 0, 500, 0))
        t.assistant(usage=(0, 0, 1, 0), stop="end_turn")
        t.turn_duration()
        self.build(t)
        tmp = self.home.parent / "fake"
        tmp.mkdir(exist_ok=True)
        (tmp / "fake_claude.py").write_text(FAKE, encoding="utf-8")
        self.resp, self.calls = tmp / "resp.json", tmp / "calls.json"
        self.cmd = [sys.executable, str(tmp / "fake_claude.py"), str(self.resp), str(self.calls), "--tools", ""]

    def respond(self, obj):
        self.resp.write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def run_analysis(self, obj, **kw):
        self.respond(obj)
        return analysis.analyze(self.home, self.repo, self.model(), self.FID, cmd=self.cmd, **kw)

    def good(self, **over):
        out = {"statements": [
            {"type": "fact", "text": "A feature tem 2 turnos.", "evidence": ["M-turns"],
             "numbers": [{"metric": "M-turns", "value": 2}]},
            {"type": "association", "text": "Houve escrita executável e uma verificação.",
             "evidence": ["M-lines-added", "M-first-pass-at"]},
            {"type": "hypothesis", "text": "Talvez o contexto grande tenha relação com o tamanho da leitura.",
             "evidence": ["M-ctx-peak"]},
            {"type": "unsupported", "text": "Nada indica o efeito do Grill Me.", "evidence": []}],
            "limitations": ["Amostra de uma feature."]}
        out.update(over)
        return out

    def events(self, typ="analysis.generated"):
        return [r["data"] for r in Wal(self.home).read() if r["type"] == typ]


class InputTests(AnalysisBase):
    def test_entrada_so_tem_fatos_e_metricas_estruturados(self):
        inp = analysis.build_input(self.model(), self.FID, self.repo)
        text = json.dumps(inp, ensure_ascii=False)
        for forbidden in ("segredo", "manage.py", "usd"):
            self.assertNotIn(forbidden, text.lower())
        self.assertEqual(set(inp), {"promptVersion", "feature", "metrics", "coverage", "facts"})
        self.assertTrue(all(m["id"].startswith("M-") and {"value", "lowerBound", "unit"} <= set(m) for m in inp["metrics"]))
        self.assertTrue(all(f["id"].startswith("F-") for f in inp["facts"]))
        self.assertEqual(inp["feature"]["id"], self.FID)
        self.assertEqual(analysis.input_hash(inp), analysis.input_hash(analysis.build_input(self.model(), self.FID, self.repo)))

    def test_lacunas_entram_com_ids_estaveis(self):
        Wal(self.home).append([{"type": "coverage.gap", "source": "manual", "data": {
            "source": "claude-code", "from": "2026-09-22T00:00:00Z", "to": "2026-09-23T00:00:00Z",
            "reason": "hook-failed", "recovered": False}}])
        inp = analysis.build_input(self.model(), self.FID, self.repo)
        self.assertEqual(inp["coverage"], [{"id": "G-1", "reason": "hook-failed", "recovered": False}])
        self.assertTrue(any(m["lowerBound"] for m in inp["metrics"]))


class ExecutionTests(AnalysisBase):
    def test_roda_fora_do_repositorio_com_ferramentas_desligadas(self):
        accepted, reasons, _ = self.run_analysis(self.good())
        self.assertTrue(accepted, reasons)
        call = json.loads(self.calls.read_text(encoding="utf-8"))
        self.assertEqual(Path(call["cwd"]).resolve(), (self.home / "analysis-cwd").resolve())
        self.assertNotIn(str(self.repo), call["cwd"])
        self.assertIn("--tools", call["argv"])
        self.assertIn('"promptVersion": "1"', call["stdin"])
        self.assertNotIn("SEGREDO", call["stdin"])

    def test_falha_do_claude_nao_grava_evento(self):
        import os
        os.environ["FAKE_FAIL"] = "1"
        self.addCleanup(os.environ.pop, "FAKE_FAIL", None)
        with self.assertRaises(analysis.AnalysisError):
            self.run_analysis(self.good())
        self.assertEqual(self.events(), [])

    def test_comando_ausente(self):
        with self.assertRaises(analysis.AnalysisError):
            analysis.run_claude("x", self.home, cmd=["comando-que-nao-existe-xyz"])

    def test_saida_em_cerca_markdown_e_aceita(self):
        accepted, reasons, _ = self.run_analysis("```json\n" + json.dumps(self.good()) + "\n```")
        self.assertTrue(accepted, reasons)


class ValidationTests(AnalysisBase):
    def reject(self, obj, needle):
        accepted, reasons, out = self.run_analysis(obj)
        self.assertFalse(accepted)
        self.assertIsNone(out)
        self.assertIn(needle, " ".join(reasons))
        ev = self.events()[-1]
        self.assertEqual((ev["accepted"], bool(ev["rejectReasons"])), (False, True))

    def test_aceita_e_registra_o_evento(self):
        accepted, reasons, out = self.run_analysis(self.good())
        self.assertTrue(accepted, reasons)
        (ev,) = self.events()
        self.assertEqual((ev["featureId"], ev["model"], ev["promptVersion"], ev["accepted"]),
                         (self.FID, "claude-sonnet-5", "1", True))
        self.assertEqual(len(ev["inputHash"]), 64)
        self.assertEqual(len(ev["outputHash"]), 64)
        self.assertNotIn("cost", json.dumps(ev).lower())
        self.assertEqual(out["statements"][0]["type"], "fact")
        self.assertTrue(Wal(self.home).verify()[0])

    def test_rejeicoes(self):
        self.reject("isto não é json", "esquema")
        self.reject(self.good(statements=[{"type": "certeza", "text": "x", "evidence": ["M-turns"]}]), "tipo")
        self.reject(self.good(statements=[{"type": "fact", "text": "x", "evidence": ["M-inexistente"]}]), "inexistente")
        self.reject(self.good(statements=[{"type": "fact", "text": "x", "evidence": []}]), "sem evidência")
        self.reject(self.good(statements=[{"type": "fact", "text": "x", "evidence": ["M-turns"],
                                           "numbers": [{"metric": "M-turns", "value": 99}]}]), "não confere")
        self.reject(self.good(limitations=[]), "limitations")

    def test_linguagem_causal_e_rejeitada(self):
        for phrase in ("O Grill Me reduziu o retrabalho.", "Isso ocorreu porque o plano era bom.",
                       "Por causa do spec, foi rápido.", "A spec causou menos correções.",
                       "Foi devido a boa leitura.", "Isso levou a menos ciclos.", "Resultou em menos tokens."):
            self.reject(self.good(statements=[{"type": "hypothesis", "text": phrase, "evidence": ["M-turns"]}]),
                        "causal")

    def test_causal_nas_limitacoes_tambem(self):
        self.reject(self.good(limitations=["Faltam dados porque houve lacunas."]), "causal")

    def test_total_para_feature_parcial_e_rejeitado(self):
        Wal(self.home).append([{"type": "coverage.gap", "source": "manual", "data": {
            "source": "claude-code", "from": "2026-09-22T00:00:00Z", "to": "2026-09-23T00:00:00Z",
            "reason": "unlogged-api-calls", "recovered": False, "sessionId": "sess-1"}}])
        self.reject(self.good(statements=[{"type": "fact", "text": "A feature consumiu 653 tokens no total.",
                                           "evidence": ["M-tokens-total"]}]), "total")

    def test_feature_historica_exige_mencao_a_especificacao(self):
        Wal(self.home).append([{"type": "feature.born", "source": "backfill", "data": {
            "featureId": self.FID, "bornAt": "2026-09-22T00:00:00Z", "bornSource": "declared",
            "dataClass": "historical", "coverage": "partial"}}])
        self.reject(self.good(), "especificação")
        accepted, reasons, _ = self.run_analysis(self.good(limitations=["Sem os custos de especificação (Copilot)."]))
        self.assertTrue(accepted, reasons)

    def test_reanalise_gera_evento_novo_sem_apagar_o_anterior(self):
        self.run_analysis(self.good())
        first = Wal(self.home).read()
        self.run_analysis(self.good(limitations=["Outra limitação."]))
        recs = Wal(self.home).read()
        self.assertEqual(recs[:len(first)], first)
        self.assertEqual(len(self.events()), 2)
        latest = analysis.latest_accepted(self.repo, self.model(), self.FID)
        self.assertEqual(latest["limitations"], ["Outra limitação."])

    def test_analise_rejeitada_nao_altera_o_relatorio(self):
        self.run_analysis(self.good())
        _, before, _ = self.cli("report", self.FID, "--no-write", "--repo", str(self.repo))
        self.assertIn("A feature tem 2 turnos.", before)
        self.assertIn("**fact**", before)
        self.run_analysis(self.good(statements=[{"type": "fact", "text": "Isso ocorreu porque sim.",
                                                 "evidence": ["M-turns"]}]))
        _, after, _ = self.cli("report", self.FID, "--no-write", "--repo", str(self.repo))
        self.assertIn("A feature tem 2 turnos.", after)   # continua a última análise ACEITA
        self.assertNotIn("porque sim", after)


class AnalyzeCommandTests(AnalysisBase):
    def analyze_cli(self, obj, *extra):
        self.respond(obj)
        from unittest import mock
        with mock.patch.object(analysis, "default_command", lambda m=None: self.cmd):
            return self.cli("analyze", self.FID, "--repo", str(self.repo), *extra)

    def test_analyze_aceita_reescreve_a_secao_analise(self):
        code, out, _ = self.analyze_cli(self.good())
        self.assertEqual(code, 0, out)
        text = (self.repo / ".ai-metrics" / "reports" / "007-x.md").read_text(encoding="utf-8")
        self.assertIn("## Análise", text)
        self.assertIn("**association**", text)
        self.assertIn("Amostra de uma feature.", text)
        self.assertNotIn("Nenhuma análise gerada", text)

    def test_analyze_rejeitada_lista_motivos_e_sai_com_1(self):
        code, out, err = self.analyze_cli(self.good(limitations=[]))
        self.assertEqual(code, 1)
        self.assertIn("limitations", out + err)
        self.assertFalse((self.repo / ".ai-metrics" / "reports" / "007-x.md").exists())


if __name__ == "__main__":
    unittest.main()
