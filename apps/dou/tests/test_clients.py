import json
import urllib.error
from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.monitoring.clients import FetchError

from apps.dou.clients import fetch_resenha


def _mock_response(body: bytes, status: int = 200):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.status = status
    response.read.return_value = body
    response.headers.get_content_charset.return_value = 'utf-8'
    return response


class FetchResenhaTest(SimpleTestCase):
    @patch('apps.dou.clients.urllib.request.urlopen')
    def test_returns_none_when_not_yet_published(self, mock_urlopen):
        body = json.dumps({'response': {'docs': []}}).encode('utf-8')
        mock_urlopen.return_value = _mock_response(body)
        result = fetch_resenha(date(2026, 7, 14), timeout=5, user_agent='test')
        self.assertIsNone(result)

    @patch('apps.dou.clients.urllib.request.urlopen')
    def test_returns_html_when_available(self, mock_urlopen):
        body = json.dumps({'response': {'docs': [{'conteudo': ['<b>Editais</b>']}]}}).encode('utf-8')
        mock_urlopen.return_value = _mock_response(body)
        result = fetch_resenha(date(2026, 7, 14), timeout=5, user_agent='test')
        self.assertEqual(result, {'source': 'resenha', 'html': '<b>Editais</b>'})

    @override_settings(REQUEST_RETRY_ATTEMPTS=1)
    @patch('apps.dou.clients.urllib.request.urlopen')
    def test_network_error_raises_fetch_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError('boom')
        with self.assertRaises(FetchError):
            fetch_resenha(date(2026, 7, 14), timeout=5, user_agent='test')
