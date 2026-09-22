"""Testes do cliente da Bot API e do canal de notificação Telegram (HTTP sempre mockado)."""
import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from apps.notifications.channels.telegram import send_telegram_document, send_telegram_message
from apps.subscribers.models import Subscriber
from apps.telegram_bot import client
from apps.telegram_bot.client import TelegramResult
from apps.telegram_bot.models import TelegramChat

from .telegram_helpers import telegram_settings


def _response(body: dict):
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode()
    resp.__enter__.return_value = resp
    return resp


@telegram_settings
class ClientTest(SimpleTestCase):
    @patch('apps.telegram_bot.client.urllib.request.urlopen')
    def test_send_message_payload(self, mock_urlopen):
        mock_urlopen.return_value = _response({'ok': True, 'result': {'message_id': 9}})
        result = client.send_message(42, 'oi')
        self.assertTrue(result.ok)
        request = mock_urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith('/bot123:ABC/sendMessage'))
        self.assertEqual(
            json.loads(request.data),
            {'chat_id': 42, 'text': 'oi', 'disable_web_page_preview': True},
        )

    @patch('apps.telegram_bot.client.urllib.request.urlopen')
    def test_api_error_becomes_result(self, mock_urlopen):
        body = json.dumps({'ok': False, 'error_code': 403, 'description': 'Forbidden: bot was blocked by the user'})
        mock_urlopen.side_effect = urllib.error.HTTPError('u', 403, 'Forbidden', {}, io.BytesIO(body.encode()))
        result = client.send_message(42, 'oi')
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, 403)
        self.assertTrue(result.is_blocked)

    @patch('apps.telegram_bot.client.urllib.request.urlopen')
    def test_network_error_never_leaks_token(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError('https://api.telegram.org/bot123:ABC/sendMessage')
        with self.assertLogs('apps.telegram_bot.client', level='WARNING') as logs:
            result = client.send_message(42, 'oi')
        self.assertFalse(result.ok)
        self.assertIsNone(result.error_code)
        self.assertNotIn('123:ABC', result.description + ' '.join(logs.output))

    def test_chat_not_found_counts_as_blocked(self):
        self.assertTrue(TelegramResult(ok=False, error_code=400, description='Bad Request: chat not found').is_blocked)
        self.assertFalse(TelegramResult(ok=False, error_code=400, description='message is too long').is_blocked)


@telegram_settings
class TelegramChannelTest(TestCase):
    def setUp(self):
        self.chat = TelegramChat.objects.create(
            chat_id=42, chat_type='private', title='Ana',
            subscriber=Subscriber.objects.create(name='Ana'),
        )

    @patch('apps.telegram_bot.client.send_message', return_value=TelegramResult(ok=True))
    def test_sent(self, mock_send):
        self.assertEqual(send_telegram_message('42', 'olá'), ('sent', None))

    @patch('apps.telegram_bot.client.send_message', return_value=TelegramResult(ok=True))
    def test_long_body_is_truncated_keeping_process_link(self, mock_send):
        send_telegram_message('42', 'x' * 5000, process_url='https://sei.cade.gov.br/p')
        text = mock_send.call_args.args[1]
        self.assertEqual(len(text), client.MAX_MESSAGE_LENGTH)
        self.assertTrue(text.endswith('https://sei.cade.gov.br/p'))

    @patch('apps.telegram_bot.client.send_message',
           return_value=TelegramResult(ok=False, error_code=403, description='blocked'))
    def test_blocked_marks_chat_unreachable(self, _mock):
        status, _ = send_telegram_message('42', 'olá')
        self.assertEqual(status, 'invalid_recipient')
        self.chat.refresh_from_db()
        self.assertFalse(self.chat.is_reachable)

    def test_transient_errors_stay_pending_for_retry(self):
        for code in (None, 429, 502):
            with self.subTest(code=code), patch(
                'apps.telegram_bot.client.send_message',
                return_value=TelegramResult(ok=False, error_code=code, description='x'),
            ):
                self.assertEqual(send_telegram_message('42', 'olá')[0], 'pending')

    @patch('apps.telegram_bot.client.send_message',
           return_value=TelegramResult(ok=False, error_code=400, description='bad'))
    def test_permanent_error_fails(self, _mock):
        self.assertEqual(send_telegram_message('42', 'olá')[0], 'failed')

    @patch('apps.telegram_bot.client.send_document', return_value=TelegramResult(ok=True))
    def test_document(self, mock_doc):
        self.assertEqual(send_telegram_document('42', 'https://sei/doc.pdf', 'doc.pdf'), ('sent', None))
        mock_doc.assert_called_once_with('42', 'https://sei/doc.pdf', 'doc.pdf')
        self.assertEqual(send_telegram_document('42', '', 'x')[0], 'failed')

    def test_disabled_channel(self):
        with self.settings(TELEGRAM_ENABLED=False):
            self.assertEqual(send_telegram_message('42', 'olá')[0], 'channel_not_configured')
