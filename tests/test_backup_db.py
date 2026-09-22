"""
Testes do comando backup_db por vendor (spec 005, contracts/backup-db.md).
pg_dump é sempre mockado — nenhum processo externo é executado.
"""
import sqlite3
import subprocess
import tempfile
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

CMD = 'apps.monitoring.management.commands.backup_db'
PG_SETTINGS = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'cade', 'USER': 'cade', 'PASSWORD': 'SenhaSecreta',
        'HOST': 'db.example', 'PORT': '5432', 'OPTIONS': {'sslmode': 'require'},
    }
}


class BackupDbTestBase(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.dest = self.tmp / 'backups'

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args):
        out = StringIO()
        call_command('backup_db', '--dest', str(self.dest), *args, stdout=out)
        return out.getvalue()


class BackupDbSqliteTest(BackupDbTestBase):
    def _settings(self, sqlite_path):
        return SimpleNamespace(SQLITE_PATH=str(sqlite_path), BASE_DIR=self.tmp)

    def test_sqlite_backup_and_rotation(self):
        src = self.tmp / 'src.sqlite3'
        conn = sqlite3.connect(src)
        conn.execute('CREATE TABLE t (x INTEGER)')
        conn.close()  # `with` não fecha a conexão; no Windows o arquivo ficaria travado
        self.dest.mkdir()
        for i in range(3):
            (self.dest / f'cade-monitor_2000010{i}_000000.sqlite3').write_bytes(b'')
        (self.dest / 'cade-monitor_20000101_000000.dump').write_bytes(b'')  # outro vendor

        with patch(f'{CMD}.connection', MagicMock(vendor='sqlite')), \
             patch(f'{CMD}.settings', self._settings(src)):
            output = self._run('--keep', '2')

        self.assertIn('Backup criado', output)
        self.assertEqual(len(list(self.dest.glob('*.sqlite3'))), 2)
        self.assertTrue((self.dest / 'cade-monitor_20000101_000000.dump').exists())

    def test_sqlite_missing_file(self):
        with patch(f'{CMD}.connection', MagicMock(vendor='sqlite')), \
             patch(f'{CMD}.settings', self._settings(self.tmp / 'nao-existe.sqlite3')), \
             self.assertRaisesMessage(CommandError, 'Banco não encontrado'):
            self._run()


class BackupDbPostgresTest(BackupDbTestBase):
    def setUp(self):
        super().setUp()
        pg_settings = SimpleNamespace(DATABASES=PG_SETTINGS, BASE_DIR=self.tmp)
        for p in (
            patch(f'{CMD}.connection', MagicMock(vendor='postgresql')),
            patch(f'{CMD}.settings', pg_settings),
        ):
            p.start()
            self.addCleanup(p.stop)

    @patch(f'{CMD}.shutil.which', return_value=None)
    def test_without_pg_dump_warns_and_exits_ok(self, _which):
        output = self._run()
        self.assertIn('pg_dump não encontrado', output)
        self.assertFalse(self.dest.exists())

    @patch(f'{CMD}.shutil.which', return_value='/usr/bin/pg_dump')
    @patch(f'{CMD}.subprocess.run')
    def test_pg_dump_success_keeps_password_out_of_argv(self, mock_run, _which):
        def fake_run(cmd, env, **kwargs):
            Path(cmd[cmd.index('-f') + 1]).write_bytes(b'PGDMP')
            return subprocess.CompletedProcess(cmd, 0, '', '')
        mock_run.side_effect = fake_run

        output = self._run()

        self.assertIn('Backup criado', output)
        cmd = mock_run.call_args.args[0]
        env = mock_run.call_args.kwargs['env']
        self.assertNotIn('SenhaSecreta', ' '.join(cmd))
        self.assertEqual(env['PGPASSWORD'], 'SenhaSecreta')
        self.assertEqual(env['PGSSLMODE'], 'require')
        self.assertIn('-Fc', cmd)
        self.assertEqual(len(list(self.dest.glob('*.dump'))), 1)

    @patch(f'{CMD}.shutil.which', return_value='/usr/bin/pg_dump')
    @patch(f'{CMD}.subprocess.run')
    def test_pg_dump_failure_removes_partial_file_and_masks_password(self, mock_run, _which):
        def fake_run(cmd, env, **kwargs):
            Path(cmd[cmd.index('-f') + 1]).write_bytes(b'parcial')
            return subprocess.CompletedProcess(cmd, 1, '', 'server version mismatch SenhaSecreta')
        mock_run.side_effect = fake_run

        with self.assertRaises(CommandError) as ctx:
            self._run()

        self.assertIn('Falha no pg_dump', str(ctx.exception))
        self.assertNotIn('SenhaSecreta', str(ctx.exception))
        self.assertEqual(list(self.dest.glob('*.dump')), [])
