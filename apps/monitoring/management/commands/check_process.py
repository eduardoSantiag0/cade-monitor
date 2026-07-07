"""
Checa um processo específico pelo ID.

Uso:
    python manage.py check_process --id 1
    python manage.py check_process --id 1 --notify-initial
"""
from django.core.management.base import BaseCommand, CommandError

from apps.monitoring.services import run_check
from apps.processes.models import MonitoredProcess


class Command(BaseCommand):
    help = 'Checa um processo específico pelo ID.'

    def add_arguments(self, parser):
        parser.add_argument('--id', type=int, required=True, help='ID do processo.')
        parser.add_argument(
            '--notify-initial',
            action='store_true',
            help='Notifica assinantes mesmo na primeira leitura (baseline).',
        )

    def handle(self, *args, **options):
        process_id = options['id']
        try:
            process = MonitoredProcess.objects.get(pk=process_id)
        except MonitoredProcess.DoesNotExist:
            raise CommandError(f'Processo #{process_id} não encontrado.')

        self.stdout.write(f'Checando: {process.label} (#{process.pk})')
        result = run_check(process, notify_initial=options['notify_initial'])

        msg = result.get('message', '')
        if result.get('changed'):
            self.stdout.write(self.style.WARNING(f'MUDANÇA DETECTADA: {msg}'))
        elif result.get('ok'):
            self.stdout.write(self.style.SUCCESS(f'OK: {msg}'))
        else:
            self.stdout.write(self.style.ERROR(f'ERRO: {msg}'))
            raise SystemExit(1)
