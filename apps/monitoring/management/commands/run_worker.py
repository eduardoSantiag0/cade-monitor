"""
Worker de monitoramento contínuo.

Executa um loop que, a cada tick:
  1. Busca processos ativos com checagem vencida
  2. Verifica um por um (sequencial — evita lock de SQLite)
  3. Envia notificações pendentes
  4. Dorme pelo WORKER_TICK_SECONDS antes de repetir

Uso:
    python manage.py run_worker
    python manage.py run_worker --once   (executa um único ciclo e encerra)

Em Docker Compose, este comando roda no serviço `worker` com restart=unless-stopped.
"""
import logging
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Inicia o worker de monitoramento contínuo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Executa um único ciclo e encerra (útil para cron).',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('CADE Monitor worker iniciado.'))
        self._running = True

        signal.signal(signal.SIGTERM, self._request_shutdown)
        signal.signal(signal.SIGINT, self._request_shutdown)

        once = options['once']

        while self._running:
            try:
                self._run_cycle()
            except Exception as exc:
                logger.error('[worker] Erro inesperado no ciclo: %s', exc, exc_info=True)

            if once:
                break

            # Sleep em passos de 1s para responder ao SIGTERM rapidamente
            for _ in range(max(1, settings.WORKER_TICK_SECONDS)):
                if not self._running:
                    break
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS('Worker encerrado.'))

    def _request_shutdown(self, signum, frame):
        self.stdout.write('\nSinal recebido. Encerrando após o ciclo atual...')
        self._running = False

    def _run_cycle(self):
        from apps.monitoring.scheduler import get_due_processes
        from apps.monitoring.services import run_check
        from apps.notifications.services import send_pending_notifications

        due = get_due_processes(settings.MAX_PROCESSES_PER_CYCLE)
        if not due:
            return

        logger.info('[worker] Ciclo: %d processo(s) a verificar.', len(due))

        for process in due:
            if not self._running:
                break
            try:
                result = run_check(process)
                if result.get('changed'):
                    self.stdout.write(
                        self.style.WARNING(f'  MUDANÇA #{process.pk} {process.label}: {result["message"][:120]}')
                    )
                elif not result.get('ok'):
                    self.stdout.write(
                        self.style.ERROR(f'  ERRO #{process.pk} {process.label}: {result["message"][:120]}')
                    )
            except Exception as exc:
                logger.error('[worker] Erro ao checar #%d: %s', process.pk, exc, exc_info=True)

            sleep = settings.SLEEP_BETWEEN_REQUESTS_SECONDS
            if sleep > 0 and self._running:
                time.sleep(sleep)

        # Envia notificações acumuladas neste ciclo
        try:
            stats = send_pending_notifications()
            if stats.get('total', 0) > 0:
                logger.info('[worker] Notificações: %s', stats)
        except Exception as exc:
            logger.error('[worker] Erro ao enviar notificações: %s', exc, exc_info=True)
