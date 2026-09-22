"""Testes do webhook do Telegram (contracts/webhook-and-ops.md)."""
import json
from unittest.mock import patch

from django.test import TestCase

from apps.telegram_bot.models import TelegramChat, TelegramUpdate

from .telegram_helpers import OK, SECRET, message_update, telegram_settings

URL = '/telegram/webhook/'


@telegram_settings
@patch('apps.telegram_bot.client.send_message', return_value=OK)
class WebhookTest(TestCase):
    def _post(self, payload, secret=SECRET, raw=None):
        headers = {'HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN': secret} if secret is not None else {}
        return self.client.post(
            URL, data=raw if raw is not None else json.dumps(payload),
            content_type='application/json', **headers,
        )

    def test_disabled_returns_404(self, mock_send):
        with self.settings(TELEGRAM_ENABLED=False):
            self.assertEqual(self._post(message_update('/start')).status_code, 404)

    def test_get_not_allowed(self, mock_send):
        self.assertEqual(self.client.get(URL).status_code, 405)

    def test_missing_or_wrong_secret_is_forbidden(self, mock_send):
        self.assertEqual(self._post(message_update('/start'), secret=None).status_code, 403)
        self.assertEqual(self._post(message_update('/start'), secret='errado').status_code, 403)
        mock_send.assert_not_called()
        self.assertFalse(TelegramUpdate.objects.exists())

    def test_invalid_body(self, mock_send):
        self.assertEqual(self._post(None, raw='não é json').status_code, 400)
        self.assertEqual(self._post({'sem': 'update_id'}).status_code, 400)

    def test_valid_update_is_processed(self, mock_send):
        response = self._post(message_update('/start', chat_id=77))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TelegramChat.objects.filter(chat_id=77).exists())
        mock_send.assert_called_once()

    def test_redelivery_is_idempotent(self, mock_send):
        update = message_update('/start')
        self.assertEqual(self._post(update).status_code, 200)
        self.assertEqual(self._post(update).status_code, 200)
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(TelegramUpdate.objects.count(), 1)

    @patch('apps.telegram_bot.services.handle_update', side_effect=RuntimeError('boom'))
    def test_processing_error_still_returns_200(self, _mock_handle, mock_send):
        with self.assertLogs('apps.telegram_bot.views', level='ERROR'):
            self.assertEqual(self._post(message_update('/start')).status_code, 200)

    def test_channel_posts_are_ignored(self, mock_send):
        update = {'update_id': 5, 'channel_post': {'message_id': 1, 'chat': {'id': -1, 'type': 'channel'}}}
        self.assertEqual(self._post(update).status_code, 200)
        mock_send.assert_not_called()
