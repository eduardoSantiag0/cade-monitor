import unittest
from datetime import datetime, timezone

from tools.ai_metrics import gitinfo
from tools.ai_metrics.tests.helpers import git, make_repo, write_file


class GitInfoTests(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo(self, {"README.md": "x", ".gitignore": ".ai-metrics/\n"})

    def commit(self, rel, msg="c"):
        write_file(self.repo, rel, msg)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)

    def test_criacao_do_branch_no_reflog(self):
        git(self.repo, "switch", "-q", "-c", "007-x")
        created = gitinfo.branch_created_at(self.repo, "007-x")
        delta = datetime.now(timezone.utc) - datetime.fromisoformat(created.replace("Z", "+00:00"))
        self.assertLess(abs(delta.total_seconds()), 120)
        self.assertIsNotNone(gitinfo.branch_base_sha(self.repo, "007-x"))
        self.assertIsNone(gitinfo.branch_created_at(self.repo, "nao-existe"))

    def test_branch_derivado_de_branch_de_feature(self):
        git(self.repo, "switch", "-q", "-c", "007-x")
        git(self.repo, "switch", "-q", "-c", "008-y")
        self.assertEqual(gitinfo.moved_from(self.repo, "008-y"), "007-x")
        self.assertEqual(gitinfo.moved_from(self.repo, "007-x"), "main")

    def test_merged_ignora_branch_novo_e_vazio(self):
        git(self.repo, "switch", "-q", "-c", "007-x")
        since = gitinfo.branch_created_at(self.repo, "007-x")
        self.assertFalse(gitinfo.is_merged_into(self.repo, "007-x", "main", since))
        self.commit("apps/a.py")
        self.assertFalse(gitinfo.is_merged_into(self.repo, "007-x", "main", since))
        git(self.repo, "switch", "-q", "main")
        git(self.repo, "merge", "-q", "--ff-only", "007-x")
        self.assertTrue(gitinfo.is_merged_into(self.repo, "007-x", "main", since))

    def test_merge_com_branch_apagado(self):
        git(self.repo, "switch", "-q", "-c", "007-x")
        self.commit("apps/a.py")
        self.commit("specs/007-x/tasks.md", "tarefas")
        git(self.repo, "switch", "-q", "main")
        git(self.repo, "merge", "-q", "--no-ff", "007-x", "-m", "Merge branch '007-x'")
        git(self.repo, "branch", "-q", "-D", "007-x")
        self.assertIsNotNone(gitinfo.merge_commit_for_branch(self.repo, "main", "007-x"))
        self.assertIsNone(gitinfo.merge_commit_for_branch(self.repo, "main", "007"))
        self.assertEqual(sorted(gitinfo.changed_files(self.repo, "007-x", "main")),
                         ["apps/a.py", "specs/007-x/tasks.md"])
        self.assertEqual(gitinfo.show_file(self.repo, "007-x", "main", "specs/007-x/tasks.md"), "tarefas")

    def test_changed_files_de_branch_existente(self):
        git(self.repo, "switch", "-q", "-c", "007-x")
        self.commit("apps/a.py")
        self.assertEqual(gitinfo.changed_files(self.repo, "007-x", "main"), ["apps/a.py"])
        self.assertEqual(gitinfo.changed_files(self.repo, "nao-existe", "main"), [])
        self.assertIsNone(gitinfo.show_file(self.repo, "007-x", "main", "nada.md"))

    def test_check_ignored(self):
        self.assertTrue(gitinfo.check_ignored(self.repo, ".ai-metrics/reports/x.md"))
        self.assertFalse(gitinfo.check_ignored(self.repo, "tools/ai_metrics/cli.py"))


if __name__ == "__main__":
    unittest.main()
