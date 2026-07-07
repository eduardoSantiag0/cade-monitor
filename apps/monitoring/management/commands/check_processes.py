"""
Executa uma rodada de checagem para todos os processos ativos vencidos.
Útil como cron job ou chamada manual.

Uso:
    python manage.py check_processes
    python manage.py check_processes --max 10
"""
from django.core.management.base import BaseCommand

from apps.monitoring.services import run_check_for_due_processes


class Command(BaseCommand):
    help = 'Executa uma rodada de checagem para todos os processos ativos vencidos.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max',
            type=int,
            default=None,
            metavar='N',
            help='Número máximo de processos a checar nesta rodada.',
        )

    def handle(self, *args, **options):
        results = run_check_for_due_processes(options.get('max'))

        if not results:
            self.stdout.write('Nenhum processo vencido para checar.')
            return

        for result in results:
            pid = result.get('process_id', '?')
            label = result.get('label', '?')
            msg = result.get('message', '')
            if result.get('changed'):
                self.stdout.write(self.style.WARNING(f'#{pid} {label}: MUDANÇA — {msg[:120]}'))
            elif result.get('ok'):
                self.stdout.write(f'#{pid} {label}: OK')
            else:
                self.stdout.write(self.style.ERROR(f'#{pid} {label}: ERRO — {msg[:120]}'))
