"""
Remove snapshots antigos para manter o banco de dados compacto.

Por padrão, mantém os N snapshots mais recentes por processo,
onde N é definido por MAX_SNAPSHOTS_PER_PROCESS no .env.

Snapshots vinculados a DetectedChange não são removidos pelo CASCADE normal,
mas isso é aceitável — a mudança mantém o contexto histórico.

Uso:
    python manage.py cleanup_snapshots
    python manage.py cleanup_snapshots --keep 50
    python manage.py cleanup_snapshots --dry-run
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.monitoring.models import PageSnapshot
from apps.processes.models import MonitoredProcess


class Command(BaseCommand):
    help = 'Remove snapshots antigos, mantendo os N mais recentes por processo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep',
            type=int,
            default=None,
            help='Snapshots a manter por processo (padrão: MAX_SNAPSHOTS_PER_PROCESS).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o que seria removido sem apagar nada.',
        )

    def handle(self, *args, **options):
        keep = options.get('keep') or settings.MAX_SNAPSHOTS_PER_PROCESS
        dry_run = options['dry_run']
        total_deleted = 0

        for process in MonitoredProcess.objects.all():
            ids_to_keep = list(
                PageSnapshot.objects
                .filter(process=process)
                .order_by('-fetched_at')
                .values_list('id', flat=True)[:keep]
            )
            to_delete = PageSnapshot.objects.filter(process=process).exclude(id__in=ids_to_keep)
            count = to_delete.count()

            if count == 0:
                continue

            if dry_run:
                self.stdout.write(f'  [{process.label}] removeria {count} snapshot(s).')
            else:
                deleted, _ = to_delete.delete()
                total_deleted += deleted

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry-run: nenhuma alteração realizada.'))
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Limpeza concluída: {total_deleted} snapshot(s) removido(s).')
            )
