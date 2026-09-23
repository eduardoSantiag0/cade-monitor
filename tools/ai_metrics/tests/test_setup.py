import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from tools.ai_metrics import cli, setup
from tools.ai_metrics.tests.helpers import make_repo, tmp_dir

MAIN = Path(setup.__file__).with_name("__main__.py")


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.repo = tmp_dir(self)
        self.home = tmp_dir(self) / "home"
        self.projects = tmp_dir(self)
        self.settings = self.repo / ".claude" / "settings.local.json"

    def run_cli(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--home", str(self.home), "setup", "--repo", str(self.repo),
                             "--projects-dir", str(self.projects), *extra])
        return code, out.getvalue() + err.getvalue()

    def data(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def stop_commands(self):
        return [h["command"] for g in self.data()["hooks"]["Stop"] for h in g["hooks"]]

    def test_cria_arquivo_pasta_e_hook_com_caminhos_absolutos(self):
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertTrue(self.home.is_dir())
        (cmd,) = self.stop_commands()
        self.assertIn(Path(setup.sys.executable).as_posix(), cmd)
        self.assertIn(MAIN.as_posix(), cmd)
        self.assertTrue(cmd.endswith("ingest --hook"))
        self.assertEqual(self.data()["hooks"]["Stop"][0]["hooks"][0]["type"], "command")

    def test_mescla_preservando_outras_chaves_e_hooks_com_backup(self):
        original = {"enabledPlugins": {"x": True}, "permissions": {"allow": ["Bash(ls)"]},
                    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo outro"}]}],
                              "PreToolUse": [{"matcher": "Bash", "hooks": []}]}}
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps(original), encoding="utf-8")
        self.assertEqual(self.run_cli()[0], 0)
        d = self.data()
        self.assertEqual(d["enabledPlugins"], {"x": True})
        self.assertEqual(d["permissions"], original["permissions"])
        self.assertEqual(d["hooks"]["PreToolUse"], original["hooks"]["PreToolUse"])
        self.assertEqual(len(self.stop_commands()), 2)
        self.assertIn("echo outro", self.stop_commands())
        bak = self.settings.with_name("settings.local.json.bak")
        self.assertEqual(json.loads(bak.read_text(encoding="utf-8")), original)

    def test_idempotente(self):
        self.run_cli()
        before = self.settings.read_text(encoding="utf-8")
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)
        self.assertEqual(len(self.stop_commands()), 1)
        self.assertIn("já instalado", out)

    def test_atualiza_entrada_propria_quando_o_python_muda(self):
        self.run_cli()
        with mock.patch.object(setup.sys, "executable", "C:/outro/python.exe"):
            self.run_cli()
        (cmd,) = self.stop_commands()
        self.assertIn("C:/outro/python.exe", cmd)

    def test_json_invalido_aborta_sem_alterar(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{quebrado", encoding="utf-8")
        code, out = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{quebrado")
        self.assertFalse(self.settings.with_name("settings.local.json.bak").exists())

    def test_dry_run_nao_grava(self):
        code, out = self.run_cli("--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(self.settings.exists())
        self.assertFalse(self.home.exists())
        self.assertIn("Stop", out)

    def test_check(self):
        self.assertEqual(self.run_cli("--check")[0], 1)
        self.run_cli()
        self.assertEqual(self.run_cli("--check")[0], 0)

    def test_remove_tira_so_a_entrada_da_ferramenta(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo outro"}]}]}}), encoding="utf-8")
        self.run_cli()
        self.assertEqual(self.run_cli("--remove")[0], 0)
        self.assertEqual(self.stop_commands(), ["echo outro"])
        (self.home / "wal.jsonl").write_text("x", encoding="utf-8")
        self.assertTrue((self.home / "wal.jsonl").exists())  # o histórico é mantido

    def test_remove_sozinho_limpa_as_chaves_vazias(self):
        self.run_cli()
        self.run_cli("--remove")
        self.assertEqual(self.data(), {})

    def test_avisa_se_ai_metrics_nao_esta_ignorado(self):
        code, out = self.run_cli()
        self.assertIn("AVISO", out)
        repo = make_repo(self, {".gitignore": ".ai-metrics/\n"})
        self.repo, self.settings = repo, repo / ".claude" / "settings.local.json"
        self.assertNotIn(".ai-metrics/ não está ignorado", self.run_cli()[1])

    def test_so_escreve_em_claude_settings_local(self):
        self.run_cli()
        files = sorted(p.relative_to(self.repo).as_posix() for p in self.repo.rglob("*") if p.is_file())
        self.assertEqual(files, [".claude/settings.local.json"])

    def test_faz_primeira_captura(self):
        from tools.ai_metrics import ingest
        from tools.ai_metrics.tests.helpers import Transcript
        t = Transcript(self.repo)
        t.prompt()
        t.assistant(stop="end_turn")
        t.write(self.projects / ingest.slug(self.repo) / "s.jsonl")
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("turn=1", out)


if __name__ == "__main__":
    unittest.main()
