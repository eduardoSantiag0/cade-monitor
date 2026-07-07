"""
Backup live-safe do banco SQLite usando sqlite3.Connection.backup().

O método backup() da stdlib suporta WAL mode e funciona enquanto o banco
está em uso — sem precisar parar o servidor ou o worker.

Uso:
    python manage.py backup_db
    python manage.py backup_db --dest /app/backups
    python manage.py backup_db --dest /app/backups --keep 7
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Cria um backup live-safe do banco SQLite.'

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
        src_path = Path(settings.SQLITE_PATH)
        if not src_path.exists():
            raise CommandError(f'Banco não encontrado: {src_path}')

        dest_dir = Path(options['dest']) if options['dest'] else settings.BASE_DIR / 'backups'
        dest_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest_path = dest_dir / f'cade-monitor_{timestamp}.sqlite3'

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

        size_kb = dest_path.stat().st_size // 1024
        self.stdout.write(
            self.style.SUCCESS(f'Backup criado: {dest_path} ({size_kb} KB)')
        )

        # Remove backups antigos se --keep > 0
        keep = options['keep']
        if keep > 0:
            existing = sorted(dest_dir.glob('cade-monitor_*.sqlite3'))
            to_remove = existing[:-keep] if len(existing) > keep else []
            for old in to_remove:
                old.unlink()
                self.stdout.write(f'Backup antigo removido: {old.name}')
