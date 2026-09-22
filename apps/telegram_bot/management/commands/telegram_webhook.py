"""
Registra, consulta ou remove o webhook do bot no Telegram.

Uso:
    python manage.py telegram_webhook            # setWebhook + setMyCommands
    python manage.py telegram_webhook --info     # getWebhookInfo
    python manage.py telegram_webhook --delete   # deleteWebhook
    python manage.py telegram_webhook --url https://meu-tunel.example   # base alternativa

O token nunca é impresso.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.telegram_bot import client


class Command(BaseCommand):
    help = 'Registra (padrão), consulta (--info) ou remove (--delete) o webhook do bot do Telegram.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--info', action='store_true', help='Mostra o estado atual do webhook.')
        group.add_argument('--delete', action='store_true', help='Remove o webhook.')
        parser.add_argument('--url', default='', help='URL base pública (padrão: BASE_URL).')

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError('TELEGRAM_BOT_TOKEN não configurado.')

        if options['info']:
            info = self._ok(client.get_webhook_info(), 'getWebhookInfo').result or {}
            self.stdout.write(f"URL: {info.get('url') or '(nenhuma)'}")
            self.stdout.write(f"Pendentes: {info.get('pending_update_count', 0)}")
            if info.get('last_error_message'):
                self.stdout.write(self.style.WARNING(f"Último erro: {info['last_error_message']}"))
            return

        if options['delete']:
            self._ok(client.delete_webhook(), 'deleteWebhook')
            self.stdout.write(self.style.SUCCESS('Webhook removido.'))
            return

        base = (options['url'] or settings.BASE_URL).rstrip('/')
        if not base.startswith('https://'):
            raise CommandError('Informe BASE_URL (ou --url) com https:// — o Telegram exige HTTPS.')
        if not settings.TELEGRAM_WEBHOOK_SECRET:
            raise CommandError('TELEGRAM_WEBHOOK_SECRET não configurado.')

        url = base + reverse('telegram_bot:webhook')
        self._ok(client.set_webhook(url, settings.TELEGRAM_WEBHOOK_SECRET), 'setWebhook')
        self._ok(client.set_my_commands(), 'setMyCommands')
        self.stdout.write(self.style.SUCCESS(f'Webhook registrado em {url} e comandos publicados.'))

    def _ok(self, result, method):
        if not result.ok:
            raise CommandError(f'{method} falhou: {result.error_code or "rede"} {result.description}')
        return result
