import urllib.error
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from apps.monitoring.clients import FetchError

from apps.dashboard.hub import (
    pauta_do_html, pauta_url, proxima_sessao, refresh_pauta, refresh_sessoes, sessoes_do_html,
)
from apps.dashboard.tests.fixtures import load_fixture


def _mock_response(body: bytes, status: int = 200):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.status = status
    response.read.return_value = body
    response.headers.get_content_charset.return_value = 'utf-8'
    return response


class SessoesDoHtmlTest(SimpleTestCase):
    def test_extracts_data_and_titulo(self):
        html = load_fixture('calendario_sessoes.html')
        result = sessoes_do_html(html)
        self.assertIn(('2020-10-05', '100ª Sessão Ordinária'), result)
        self.assertIn(('2099-10-05', '999ª Sessão Ordinária'), result)


class PautaDoHtmlTest(SimpleTestCase):
    def test_returns_url_when_pdf_present(self):
        html = load_fixture('pautas_2099_com_pdf.html')
        url = pauta_do_html(html, 2099, 999)
        self.assertEqual(url, 'https://cdn.cade.gov.br/Sessoes/2099/999/pauta-999.pdf')

    def test_returns_empty_when_pdf_absent(self):
        html = load_fixture('pautas_2099_sem_pdf.html')
        self.assertEqual(pauta_do_html(html, 2099, 999), '')


class RefreshSessoesTest(TestCase):
    def setUp(self):
        cache.clear()

    @patch('apps.dashboard.hub.urllib.request.urlopen')
    def test_populates_cache_and_respects_min_interval(self, mock_urlopen):
        html = load_fixture('calendario_sessoes.html')
        mock_urlopen.return_value = _mock_response(html.encode('utf-8'))

        refresh_sessoes(timeout=5, user_agent='test')
        self.assertEqual(mock_urlopen.call_count, 1)
        self.assertIsNotNone(cache.get('hub:sessoes'))

        refresh_sessoes(timeout=5, user_agent='test')
        self.assertEqual(mock_urlopen.call_count, 1, 'segunda tentativa dentro do intervalo mínimo não deve buscar de novo')

    @override_settings(REQUEST_RETRY_ATTEMPTS=1)
    @patch('apps.dashboard.hub.urllib.request.urlopen')
    def test_network_error_does_not_raise(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError('boom')
        refresh_sessoes(timeout=5, user_agent='test')  # não deve lançar
        self.assertIsNone(cache.get('hub:sessoes'))


class ProximaSessaoTest(TestCase):
    def setUp(self):
        cache.clear()

    @patch('apps.dashboard.hub.urllib.request.urlopen')
    def test_returns_only_future_session_without_http(self, mock_urlopen):
        cache.set('hub:sessoes', [('2020-10-05', '100ª Sessão Ordinária'), ('2099-10-05', '999ª Sessão Ordinária')])
        result = proxima_sessao()
        self.assertEqual(result, {'data': '2099-10-05', 'titulo': '999ª Sessão Ordinária'})
        mock_urlopen.assert_not_called()

    def test_empty_cache_returns_none(self):
        self.assertIsNone(proxima_sessao())


class RefreshPautaTest(TestCase):
    def setUp(self):
        cache.clear()
        cache.set('hub:sessoes', [('2099-10-05', '999ª Sessão Ordinária')])

    @patch('apps.dashboard.hub.urllib.request.urlopen')
    def test_populates_cache_with_long_ttl_when_found(self, mock_urlopen):
        html = load_fixture('pautas_2099_com_pdf.html')
        mock_urlopen.return_value = _mock_response(html.encode('utf-8'))
        refresh_pauta(timeout=5, user_agent='test')
        self.assertEqual(cache.get('hub:pauta:2099:999'), 'https://cdn.cade.gov.br/Sessoes/2099/999/pauta-999.pdf')

    @patch('apps.dashboard.hub.urllib.request.urlopen')
    def test_second_call_within_min_interval_skips_http(self, mock_urlopen):
        html = load_fixture('pautas_2099_com_pdf.html')
        mock_urlopen.return_value = _mock_response(html.encode('utf-8'))
        refresh_pauta(timeout=5, user_agent='test')
        refresh_pauta(timeout=5, user_agent='test')
        self.assertEqual(mock_urlopen.call_count, 1)

    @override_settings(REQUEST_RETRY_ATTEMPTS=1)
    @patch('apps.dashboard.hub.urllib.request.urlopen')
    def test_network_error_does_not_raise(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError('boom')
        refresh_pauta(timeout=5, user_agent='test')  # não deve lançar
        self.assertIsNone(cache.get('hub:pauta:2099:999'))

    @patch('apps.dashboard.hub.urllib.request.urlopen')
    def test_no_future_session_skips_http(self, mock_urlopen):
        cache.clear()  # sem 'hub:sessoes'
        refresh_pauta(timeout=5, user_agent='test')
        mock_urlopen.assert_not_called()


class PautaUrlTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_reads_cache_without_http(self):
        cache.set('hub:pauta:2099:999', 'https://cdn.cade.gov.br/x/2099/999/pauta.pdf')
        sessao = {'data': '2099-10-05', 'titulo': '999ª Sessão Ordinária'}
        self.assertEqual(pauta_url(sessao), 'https://cdn.cade.gov.br/x/2099/999/pauta.pdf')

    def test_missing_cache_returns_empty_string(self):
        sessao = {'data': '2099-10-05', 'titulo': '999ª Sessão Ordinária'}
        self.assertEqual(pauta_url(sessao), '')
