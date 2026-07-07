"""
Testa a extração de texto de uma URL pública ou número de processo.
Útil para validar que uma fonte está sendo parseada corretamente.

Uso:
    python manage.py probe_process "https://sei.cade.gov.br/..."
    python manage.py probe_process "08700.005905/2026-38"
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.monitoring.clients import FetchError, get_snapshot
from apps.monitoring.extractors import latest_cade_records


class Command(BaseCommand):
    help = 'Testa a extração de texto de uma URL ou número de processo.'

    def add_arguments(self, parser):
        parser.add_argument('source', help='URL pública ou número do processo/protocolo.')

    def handle(self, *args, **options):
        source = options['source']
        self.stdout.write(f'Acessando: {source}')
        self.stdout.write(f'User-Agent: {settings.USER_AGENT}')
        self.stdout.write(f'Timeout: {settings.REQUEST_TIMEOUT_SECONDS}s')
        self.stdout.write('')

        try:
            snapshot = get_snapshot(
                source,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
                user_agent=settings.USER_AGENT,
            )
        except FetchError as exc:
            self.stdout.write(self.style.ERROR(f'Erro: {exc}'))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(f'URL final: {snapshot.url}'))
        self.stdout.write(f'Status HTTP:    {snapshot.status_code}')
        self.stdout.write(f'Hash SHA-256:   {snapshot.content_hash}')
        self.stdout.write(f'Tamanho texto:  {len(snapshot.text)} caracteres')
        self.stdout.write(f'Tamanho HTML:   {snapshot.content_length} bytes')
        self.stdout.write(f'Título:         {snapshot.title}')

        records = latest_cade_records(snapshot.text, limit=5)
        if records:
            self.stdout.write(self.style.WARNING('\nRegistros mais recentes detectados:'))
            for record in records:
                self.stdout.write(f'  {record}')
        else:
            self.stdout.write(self.style.WARNING('\nNenhum registro estruturado CADE detectado.'))
            self.stdout.write('Primeiros 1500 chars do texto extraído:')
            self.stdout.write(snapshot.text[:1500])
