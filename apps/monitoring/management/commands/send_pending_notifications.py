"""
Envia todas as notificações pendentes.
Pode ser chamado como cron job ou após um check_processes.

Uso:
    python manage.py send_pending_notifications
"""
from django.core.management.base import BaseCommand

from apps.notifications.services import send_pending_notifications


class Command(BaseCommand):
    help = 'Envia todas as notificações pendentes.'

    def handle(self, *args, **options):
        stats = send_pending_notifications()
        self.stdout.write(
            f"Total: {stats.get('total', 0)} | "
            f"Enviadas: {stats.get('sent', 0)} | "
            f"Falhas: {stats.get('failed', 0)} | "
            f"Ignoradas: {stats.get('skipped', 0)}"
        )
