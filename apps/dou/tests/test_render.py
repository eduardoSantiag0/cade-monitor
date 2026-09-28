from datetime import date, datetime

from django.test import SimpleTestCase

from apps.dou.parsers import parse_resenha_html
from apps.dou.render import render_digest_html, render_digest_text
from apps.dou.tests.fixtures import load_fixture

REF_DATE = date(2026, 7, 14)
NOW = datetime(2026, 7, 14, 9, 0)


class RenderBoldAndTruncateTest(SimpleTestCase):
    def setUp(self):
        self.dou_data = parse_resenha_html(load_fixture('resenha_com_publicacoes.json')['html'])

    def test_case_title_and_parties_are_bold_in_html(self):
        html = render_digest_html(self.dou_data, terms=[], reference_date=REF_DATE, now=NOW)
        self.assertIn('<strong>Ato de Concentração nº 08700.001234/2026-11</strong>', html)
        self.assertIn('<strong>Empresa XYZ Participações S.A.', html)

    def test_long_despacho_is_truncated(self):
        html = render_digest_html(self.dou_data, terms=[], reference_date=REF_DATE, now=NOW)
        self.assertIn('(...)', html)


class RenderHighlightTest(SimpleTestCase):
    def setUp(self):
        self.dou_data = parse_resenha_html(load_fixture('resenha_com_publicacoes.json')['html'])

    def test_monitored_term_present_is_highlighted(self):
        html = render_digest_html(self.dou_data, terms=['Empresa XYZ'], reference_date=REF_DATE, now=NOW)
        self.assertIn('background-color:#fff200', html)

    def test_no_monitored_term_no_highlight(self):
        html = render_digest_html(self.dou_data, terms=['Empresa Que Nao Existe'], reference_date=REF_DATE, now=NOW)
        self.assertNotIn('background-color:#fff200', html)


class RenderAtaFooterTest(SimpleTestCase):
    def test_ata_with_url_shows_title_and_link(self):
        dou_data = {'editais': [], 'despachos': [], 'atas': [{'titulo': 'Ata nº 27', 'url': 'https://x/ata-27'}]}
        html = render_digest_html(dou_data, terms=[], reference_date=REF_DATE, now=NOW)
        self.assertIn('Ata nº 27', html)
        self.assertIn('https://x/ata-27', html)

    def test_ata_without_url_shows_title_only(self):
        dou_data = {'editais': [], 'despachos': [], 'atas': [{'titulo': 'Ata nº 28', 'url': ''}]}
        html = render_digest_html(dou_data, terms=[], reference_date=REF_DATE, now=NOW)
        self.assertIn('Ata nº 28', html)
        self.assertNotIn('href=""', html)


class RenderNoPublicationTest(SimpleTestCase):
    def test_empty_day_has_explicit_notice(self):
        dou_data = {'editais': [], 'despachos': [], 'atas': []}
        text = render_digest_text(dou_data, terms=[], reference_date=REF_DATE, now=NOW)
        self.assertIn('Não houve publicações', text)
        html = render_digest_html(dou_data, terms=[], reference_date=REF_DATE, now=NOW)
        self.assertIn('Não houve publicações', html)
