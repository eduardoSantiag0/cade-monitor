import json
import unittest

from tools.ai_metrics import ingest
from tools.ai_metrics.tests.helpers import Transcript, tmp_dir
from tools.ai_metrics.wal import Wal


class IngestBase(unittest.TestCase):
    def setUp(self):
        self.repo = tmp_dir(self)
        self.projects = tmp_dir(self)
        self.home = tmp_dir(self)
        self.pdir = self.projects / ingest.slug(self.repo)

    def transcript(self, **kw):
        return Transcript(self.repo, **kw)

    def save(self, t, name=None):
        t.write(self.pdir / f"{name or t.session}.jsonl")

    def run_ingest(self, **kw):
        return ingest.run(self.home, self.repo, self.projects, **kw)

    def events(self, typ=None):
        recs = Wal(self.home).read()
        return [r for r in recs if typ is None or r["type"] == typ]

    def wal_text(self):
        p = self.home / "wal.jsonl"
        return p.read_text(encoding="utf-8") if p.exists() else ""


class TurnTests(IngestBase):
    def test_dedupe_por_message_id_e_uniao_de_ferramentas(self):
        t = self.transcript()
        t.prompt()
        t.assistant(tools=[("Read", "apps/a.py"), ("Edit", "apps/a.py", "x", "y\nz"), ("Bash", "ls")],
                    usage=(2, 335, 28549, 5814), msg_id="msg_1")
        t.assistant(usage=(3, 50, 30000, 10), stop="end_turn", msg_id="msg_2")
        self.save(t)
        self.run_ingest()
        turns = self.events("turn")
        self.assertEqual([r["data"]["msgId"] for r in turns], ["msg_1", "msg_2"])
        self.assertEqual([x["name"] for x in turns[0]["data"]["tools"]], ["Read", "Edit", "Bash"])
        self.assertEqual(turns[0]["data"]["usage"], {"in": 2, "out": 335, "cacheRead": 28549,
                                                      "cacheCreate": 5814, "thinking": 0})

    def test_idempotencia(self):
        t = self.transcript()
        t.prompt()
        t.assistant(tools=[("Read", "a.py")])
        t.assistant(stop="end_turn")
        t.turn_duration(1000)
        self.save(t)
        first = self.run_ingest()
        n = len(Wal(self.home).read())
        self.assertGreater(first["new"]["turn"], 0)
        second = self.run_ingest()
        self.assertEqual(sum(second["new"].values()), 0)
        self.assertEqual(len(Wal(self.home).read()), n)
        (self.home / "state.json").unlink()  # sem state.json também não duplica
        self.assertEqual(sum(self.run_ingest()["new"].values()), 0)

    def test_ultima_resposta_incompleta_e_adiada(self):
        t = self.transcript()
        t.prompt()
        t.assistant(tools=[("Bash", "ls")], msg_id="msg_1", results=False)
        self.save(t)
        self.run_ingest()
        self.assertEqual(self.events("turn"), [])
        self.run_ingest(final=True)
        self.assertEqual(len(self.events("turn")), 1)

    def test_metadados_do_turno(self):
        t = self.transcript(branch="007-x", effort="high", model="claude-sonnet-5")
        t.permission_mode("auto")
        t.prompt()
        t.assistant(usage=(1, 2, 3, 4), stop="end_turn")
        self.save(t)
        self.run_ingest()
        d = self.events("turn")[0]["data"]
        self.assertEqual((d["model"], d["effort"], d["permissionMode"], d["gitBranch"], d["sidechain"]),
                         ("claude-sonnet-5", "high", "auto", "007-x", False))
        self.assertEqual(d["stop"], "end_turn")
        self.assertEqual(self.events("turn")[0]["source"], "claude-code")

    def test_sidechain_marcado(self):
        t = self.transcript()
        t.prompt()
        t.assistant(stop="end_turn")
        for line in t.lines:
            if line["type"] == "assistant":
                line["isSidechain"] = True
        self.save(t)
        self.run_ingest()
        self.assertTrue(self.events("turn")[0]["data"]["sidechain"])

    def test_modelo_sintetico_e_ignorado(self):
        t = self.transcript()
        t.prompt()
        t.assistant(stop="end_turn", model="<synthetic>", usage=(0, 0, 0, 0))
        self.save(t)
        self.run_ingest()
        self.assertEqual(self.events("turn"), [])


class PromptAndCycleTests(IngestBase):
    def test_prompt_sem_texto_e_com_skill(self):
        t = self.transcript()
        t.prompt("segredo do usuário")
        t.prompt(skill="speckit-implement", args="T001-T005 detalhes secretos")
        t.prompt(skill="speckit-plan", args="")
        t.prompt(skill="speckit-implement", args="faça tudo")
        self.save(t)
        self.run_ingest()
        prompts = [r["data"] for r in self.events("prompt")]
        self.assertEqual([p.get("skill") for p in prompts],
                         [None, "speckit-implement", "speckit-plan", "speckit-implement"])
        self.assertEqual([p["argsKind"] for p in prompts], ["none", "task-range", "none", "other"])
        for word in ("segredo", "secretos", "faça tudo"):
            self.assertNotIn(word, self.wal_text())

    def test_comandos_locais_nao_sao_prompts(self):
        t = self.transcript()
        t.prompt(skill="model")
        t.prompt(skill="clear")
        t.prompt(skill="compact")
        self.save(t)
        self.run_ingest()
        self.assertEqual(self.events("prompt"), [])
        self.assertEqual(sorted(r["data"]["kind"] for r in self.events("context.event")),
                         ["clear", "compact"])

    def test_compactacao_por_evento_de_sistema(self):
        t = self.transcript()
        t.system("compact_boundary")
        self.save(t)
        self.run_ingest()
        self.assertEqual([r["data"]["kind"] for r in self.events("context.event")], ["compact"])

    def test_turn_end_de_turn_duration(self):
        t = self.transcript()
        t.prompt()
        t.assistant(stop="end_turn")
        t.turn_duration(164045)
        self.save(t)
        self.run_ingest()
        e = self.events("turn.end")[0]["data"]
        self.assertEqual(e["durationMs"], 164045)
        self.assertEqual(e["sessionId"], "sess-1")


class ToolSanitizeTests(IngestBase):
    def one_turn(self, tools, **kw):
        t = self.transcript()
        t.prompt()
        t.assistant(tools=tools, **kw)
        t.assistant(stop="end_turn")
        self.save(t)
        self.run_ingest()
        return self.events("turn")[0]["data"]["tools"]

    def test_bash_verificacao_e_git_sem_gravar_o_comando(self):
        tools = self.one_turn([("Bash", "python manage.py test tests --segredo123"),
                               ("Bash", "git commit -m 'mensagem-secreta'"),
                               ("Bash", "echo cat-secreto > arquivo")], is_error=(0,))
        self.assertEqual(tools[0], {"name": "Bash", "verify": {"id": "django-test", "ok": False}})
        self.assertEqual(tools[1], {"name": "Bash", "git": "commit"})
        self.assertEqual(tools[2], {"name": "Bash"})
        for word in ("segredo123", "mensagem-secreta", "cat-secreto", "manage.py"):
            self.assertNotIn(word, self.wal_text())

    def test_verificacao_verde(self):
        tools = self.one_turn([("Bash", "python -m pytest -q")])
        self.assertEqual(tools[0]["verify"], {"id": "pytest", "ok": True})

    def test_powershell_tambem_e_classificado(self):
        tools = self.one_turn([("PowerShell", "python manage.py test tests"), ("PowerShell", "git commit -m x")])
        self.assertEqual(tools[0], {"name": "PowerShell", "verify": {"id": "django-test", "ok": True}})
        self.assertEqual(tools[1], {"name": "PowerShell", "git": "commit"})

    def test_git_operation_estruturado(self):
        t = self.transcript()
        t.prompt()
        t.assistant(tools=[("Bash", "algo diferente")], results=False)
        tid = next(x["message"]["content"][0]["id"] for x in t.lines
                   if x["type"] == "assistant" and x["message"]["content"][0].get("type") == "tool_use")
        t.tool_result(tid, git_op={"commit": {"sha": "abc"}})
        t.assistant(stop="end_turn")
        self.save(t)
        self.run_ingest()
        self.assertEqual(self.events("turn")[0]["data"]["tools"][0]["git"], "commit")

    def test_caminhos_relativos_e_fora_do_repositorio(self):
        outside = str(tmp_dir(self) / "segredo" / "x.py")
        tools = self.one_turn([("Read", "apps/a.py"), ("Read", outside),
                               ("Edit", "specs/007/spec.md", "a", "b")])
        self.assertEqual(tools[0], {"name": "Read", "path": "apps/a.py"})
        self.assertEqual(tools[1], {"name": "Read", "outside": True})
        self.assertEqual(tools[2]["path"], "specs/007/spec.md")
        self.assertNotIn("segredo", self.wal_text())
        self.assertNotIn(str(self.repo).replace("\\", "\\\\"), self.wal_text())

    def test_linhas_escritas_sem_conteudo(self):
        tools = self.one_turn([("Edit", "apps/a.py", "l1\nl2\nl3", "n1\nn2"),
                               ("Write", "apps/b.py", "linha-secreta-1\nlinha-secreta-2\n")])
        self.assertEqual((tools[0]["add"], tools[0]["del"]), (2, 3))
        self.assertEqual((tools[1]["add"], tools[1]["del"]), (2, 0))
        self.assertNotIn("secreta", self.wal_text())

    def test_multiedit_conta_linhas_de_todas_as_edicoes(self):
        edits = [("a\nb", "c"), ("d", "e\nf\ng")]
        tools = self.one_turn([("MultiEdit", "apps/a.py", edits)])
        self.assertEqual((tools[0]["name"], tools[0]["path"], tools[0]["add"], tools[0]["del"]),
                         ("MultiEdit", "apps/a.py", 4, 3))

    def test_skill_por_ferramenta(self):
        tools = self.one_turn([("Skill", "grill-me")])
        self.assertEqual(tools[0], {"name": "Skill", "skill": "grill-me"})


class PrivacyTests(IngestBase):
    def test_sem_texto_livre_nem_valor_monetario(self):
        t = self.transcript()
        t.prompt("texto do prompt")
        t.assistant(tools=[("Bash", "ls")])
        t.assistant(stop="end_turn")
        t.turn_duration()
        t.cost_state({"claude-opus-5-5": (4, 200, 2000, 400)})
        self.save(t)
        self.run_ingest()
        text = self.wal_text().lower()
        for word in ("texto do prompt", "resposta", "saída", "costusd", "12.5", "usd"):
            self.assertNotIn(word, text)
        for rec in Wal(self.home).read():
            json.dumps(rec)


if __name__ == "__main__":
    unittest.main()
