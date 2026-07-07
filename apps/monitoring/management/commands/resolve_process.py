"""
Tenta resolver um número de processo para a URL pública de detalhe.

Uso:
    python manage.py resolve_process "08700.005905/2026-38"
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.monitoring.clients import resolve_process_url


class Command(BaseCommand):
    help = 'Resolve um número de processo/protocolo para a URL pública do CADE/SEI.'

    def add_arguments(self, parser):
        parser.add_argument(
            'process_number',
            help='Número do processo (ex: 08700.005905/2026-38)',
        )

    def handle(self, *args, **options):
        number = options['process_number']
        self.stdout.write(f'Resolvendo: {number}')

        url = resolve_process_url(
            number,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
            user_agent=settings.USER_AGENT,
        )

        if url:
            self.stdout.write(self.style.SUCCESS(f'URL encontrada: {url}'))
        else:
            self.stdout.write(
                self.style.WARNING(
                    'URL pública não encontrada. '
                    'O processo pode não ter página pública no SEI ou o número pode estar incorreto.'
                )
            )
