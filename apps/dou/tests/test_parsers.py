from django.test import SimpleTestCase

from apps.dou.parsers import parse_ingov_listing, parse_resenha_html, parse_sei_publications
from apps.dou.tests.fixtures import load_fixture


class ParseResenhaHtmlTest(SimpleTestCase):
    def test_extracts_editais_and_despachos_only_from_cade_orgao(self):
        data = load_fixture('resenha_com_publicacoes.json')
        result = parse_resenha_html(data['html'])
        # Seção 1 (despachos): 2 itens do CADE; a Seção 2 (Ministério da Justiça,
        # que só cita o CADE de passagem) não deve contaminar o resultado.
        self.assertEqual(len(result['despachos']), 2)
        self.assertIn('08700.001234/2026-11', result['despachos'][0]['text'])
        self.assertIn('08700.005678/2026-22', result['despachos'][1]['text'])
        # Seção 3 (editais): 2 blocos idênticos no fixture -> deduplicados para 1.
        self.assertEqual(len(result['editais']), 1)
        self.assertIn('08700.001234/2026-11', result['editais'][0]['text'])

    def test_non_cade_orgao_is_excluded(self):
        data = load_fixture('resenha_vazia.json')
        result = parse_resenha_html(data['html'])
        self.assertEqual(result, {'editais': [], 'despachos': [], 'atas': []})


class ParseIngovListingTest(SimpleTestCase):
    def test_filters_by_cade_classifies_by_arttype_and_deduplicates(self):
        data = load_fixture('ingov_listing_com_publicacoes.json')
        result = parse_ingov_listing(data['htmls'])
        # O item de "Ministério da Justiça" (não-CADE) foi descartado; os dois
        # editais idênticos do fixture foram deduplicados para 1.
        self.assertEqual(len(result['editais']), 1)
        self.assertEqual(len(result['despachos']), 1)
        self.assertIn('08700.001234/2026-11', result['editais'][0]['text'])
        self.assertIn('08700.005678/2026-22', result['despachos'][0]['text'])
        self.assertTrue(result['editais'][0]['url'].startswith('https://www.in.gov.br/web/dou/-/'))


class ParseSeiPublicationsTest(SimpleTestCase):
    def test_extracts_one_item_per_case_title(self):
        html = (
            '<div>Processo Administrativo nº 08700.001234/2026-11 texto A.</div>'
            '<div>Ato de Concentração nº 08700.005678/2026-22 texto B.</div>'
        )
        result = parse_sei_publications(html)
        self.assertEqual(len(result), 2)
        self.assertIn('08700.001234/2026-11', result[0]['text'])
        self.assertIn('08700.005678/2026-22', result[1]['text'])

    def test_page_without_any_case_title_returns_no_items(self):
        """Página de busca do SEI sem tabela de resultado (achado da validação ao
        vivo, research.md "Correção pós-implementação"): texto sem nenhuma citação de
        caso não deve virar um item inventado — deve ser tratado como "sem
        publicações", não como uma publicação de conteúdo genérico."""
        html = '<div>Menu, rodapé, script de busca — nenhuma citação de processo aqui.</div>'
        self.assertEqual(parse_sei_publications(html), [])
