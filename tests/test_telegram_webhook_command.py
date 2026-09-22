"""Testes do comando telegram_webhook (contracts/webhook-and-ops.md). Bot API mockada."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.telegram_bot.client import TelegramResult

from .telegram_helpers import SECRET, telegram_settings

OK = TelegramResult(ok=True, result=True)


@telegram_settings
class TelegramWebhookCommandTest(SimpleTestCase):
    def _run(self, *args):
        out = StringIO()
        call_command('telegram_webhook', *args, stdout=out)
        return out.getvalue()

    @patch('apps.telegram_bot.client.set_my_commands', return_value=OK)
    @patch('apps.telegram_bot.client.set_webhook', return_value=OK)
    def test_registers_webhook_and_commands(self, mock_set, mock_cmds):
        with self.settings(BASE_URL='https://monitor.example.com'):
            output = self._run()
        mock_set.assert_called_once_with('https://monitor.example.com/telegram/webhook/', SECRET)
        mock_cmds.assert_called_once()
        self.assertIn('Webhook registrado', output)
        self.assertNotIn('123:ABC', output)

    def test_requires_https_base_url(self):
        with self.settings(BASE_URL='http://inseguro.example'), self.assertRaisesMessage(CommandError, 'HTTPS'):
            self._run()

    @patch('apps.telegram_bot.client.set_webhook',
           return_value=TelegramResult(ok=False, error_code=400, description='bad webhook'))
    def test_api_failure_is_an_error(self, _mock):
        with self.assertRaisesMessage(CommandError, 'bad webhook'):
            self._run('--url', 'https://tunel.example')

    @patch('apps.telegram_bot.client.get_webhook_info', return_value=TelegramResult(
        ok=True, result={'url': 'https://x/telegram/webhook/', 'pending_update_count': 2, 'last_error_message': 'Timeout'}))
    def test_info(self, _mock):
        output = self._run('--info')
        self.assertIn('https://x/telegram/webhook/', output)
        self.assertIn('Timeout', output)

    @patch('apps.telegram_bot.client.delete_webhook', return_value=OK)
    def test_delete(self, mock_delete):
        self.assertIn('removido', self._run('--delete'))
        mock_delete.assert_called_once()

    def test_requires_token(self):
        with self.settings(TELEGRAM_BOT_TOKEN=''), self.assertRaisesMessage(CommandError, 'TELEGRAM_BOT_TOKEN'):
            self._run('--info')
