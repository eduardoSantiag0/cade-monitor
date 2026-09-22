"""
Backup do banco, conforme o vendor em uso.

- SQLite (dev/testes): backup live-safe via sqlite3.Connection.backup(), que
  suporta WAL mode e funciona com o banco em uso.
- PostgreSQL (produção): pg_dump em formato custom, se estiver no PATH. Sem
  pg_dump, apenas avisa — o backup do Postgres gerenciado é feito pelo provedor
  (Render) — e termina sem erro para não quebrar o scheduler diário.
  Contrato: specs/005-postgres-render/contracts/backup-db.md

Uso:
    python manage.py backup_db
    python manage.py backup_db --dest /app/backups
    python manage.py backup_db --dest /app/backups --keep 7
"""
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

PG_DUMP_TIMEOUT_SECONDS = 1800


class Command(BaseCommand):
    help = (
        'Cria um backup do banco: cópia live-safe no SQLite ou pg_dump no PostgreSQL '
        '(sem pg_dump no PATH, apenas avisa que o backup é gerenciado pelo provedor).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dest',
            default=None,
            help='Diretório de destino do backup (padrão: <BASE_DIR>/backups).',
        )
        parser.add_argument(
            '--keep',
            type=int,
            default=7,
            help='Número de backups anteriores a manter (padrão: 7). 0 = manter todos.',
        )

    def handle(self, *args, **options):
        dest_dir = Path(options['dest']) if options['dest'] else settings.BASE_DIR / 'backups'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if connection.vendor == 'postgresql':
            pg_dump = shutil.which('pg_dump')
            if not pg_dump:
                self.stdout.write(self.style.WARNING(
                    'AVISO: pg_dump não encontrado; o backup do PostgreSQL é gerenciado pelo '
                    'provedor (Render). Nada a fazer.'
                ))
                return
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / f'cade-monitor_{timestamp}.dump'
            self._backup_postgres(pg_dump, dest_path)
        else:
            dest_path = dest_dir / f'cade-monitor_{timestamp}.sqlite3'
            self._backup_sqlite(dest_path)

        size_kb = dest_path.stat().st_size // 1024
        self.stdout.write(
            self.style.SUCCESS(f'Backup criado: {dest_path} ({size_kb} KB)')
        )
        self._rotate(dest_dir, dest_path.suffix, options['keep'])

    def _backup_sqlite(self, dest_path: Path) -> None:
        src_path = Path(settings.SQLITE_PATH)
        if not src_path.exists():
            raise CommandError(f'Banco não encontrado: {src_path}')
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # sqlite3.Connection.backup() é live-safe: funciona com WAL mode ativo
        try:
            src_conn = sqlite3.connect(src_path)
            dst_conn = sqlite3.connect(dest_path)
            with dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()
        except Exception as exc:
            raise CommandError(f'Falha no backup: {exc}') from exc

    def _backup_postgres(self, pg_dump: str, dest_path: Path) -> None:
        db = settings.DATABASES['default']
        # Senha e sslmode vão pelo ambiente do subprocess — nunca no argv (visível no ps).
        env = {
            **os.environ,
            'PGPASSWORD': db.get('PASSWORD', ''),
            'PGSSLMODE': db.get('OPTIONS', {}).get('sslmode', 'prefer'),
        }
        cmd = [
            pg_dump, '-Fc',
            '-h', db['HOST'], '-p', str(db.get('PORT') or 5432),
            '-U', db['USER'], '-d', db['NAME'],
            '-f', str(dest_path),
        ]
        try:
            result = subprocess.run(
                cmd, env=env, capture_output=True, text=True, timeout=PG_DUMP_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            dest_path.unlink(missing_ok=True)
            raise CommandError(f'Falha no pg_dump: {exc}') from exc

        if result.returncode != 0:
            dest_path.unlink(missing_ok=True)
            stderr = (result.stderr or '').replace(env['PGPASSWORD'], '***') if env['PGPASSWORD'] else result.stderr
            raise CommandError(f'Falha no pg_dump: {(stderr or "").strip()}')

    def _rotate(self, dest_dir: Path, suffix: str, keep: int) -> None:
        """Remove backups antigos do mesmo tipo (extensão) se --keep > 0."""
        if keep <= 0:
            return
        existing = sorted(dest_dir.glob(f'cade-monitor_*{suffix}'))
        to_remove = existing[:-keep] if len(existing) > keep else []
        for old in to_remove:
            old.unlink()
            self.stdout.write(f'Backup antigo removido: {old.name}')
