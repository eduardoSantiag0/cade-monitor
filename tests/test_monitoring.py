"""
Testes do app monitoring.
Testa extractors, diff e services com mocks para chamadas HTTP.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.monitoring.diff import compute_diff
from apps.monitoring.extractors import (
    extract_movement_records,
    extract_protocol_records,
    html_to_text,
    latest_cade_records,
    normalize_text,
    stable_hash,
)
from apps.processes.models import MonitoredProcess, ProcessStatus


class NormalizeTextTest(TestCase):
    def test_removes_noise_patterns(self):
        text = 'Lista de Andamentos\nData/hora da consulta: 01/01/2024 14:00\nAndamento X'
        result = normalize_text(text, drop_noise=True)
        self.assertNotIn('Data/hora da consulta', result)
        self.assertIn('Andamento X', result)

    def test_collapses_multiple_spaces(self):
        self.assertEqual(normalize_text('a   b', drop_noise=False), 'a b')

    def test_replaces_nbsp(self):
        self.assertEqual(normalize_text('a\xa0b', drop_noise=False), 'a b')

    def test_removes_empty_lines(self):
        result = normalize_text('a\n\n\nb', drop_noise=False)
        self.assertEqual(result, 'a\nb')


class StableHashTest(TestCase):
    def test_is_deterministic(self):
        text = 'texto de teste qualquer'
        self.assertEqual(stable_hash(text), stable_hash(text))

    def test_different_inputs_give_different_hashes(self):
        self.assertNotEqual(stable_hash('A'), stable_hash('B'))

    def test_returns_64_char_hex(self):
        h = stable_hash('teste')
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in h))


class HtmlToTextTest(TestCase):
    def test_strips_script_content(self):
        html = '<body><script>alert("xss")</script><p>Texto útil</p></body>'
        text, _ = html_to_text(html)
        self.assertNotIn('alert', text)
        self.assertIn('Texto útil', text)

    def test_extracts_title(self):
        html = '<html><head><title>Meu Processo</title></head><body>X</body></html>'
        _, title = html_to_text(html)
        self.assertEqual(title, 'Meu Processo')

    def test_handles_empty_string(self):
        text, title = html_to_text('')
        self.assertEqual(text, '')
        self.assertEqual(title, '')


class ComputeDiffTest(TestCase):
    def test_detects_added_lines(self):
        old = 'Linha A\nLinha B'
        new = 'Linha A\nLinha B\nLinha C nova'
        summary, diff = compute_diff(old, new)
        self.assertIn('Linha C nova', summary)

    def test_same_text_returns_generic_result(self):
        text = 'Linha A\nLinha B'
        summary, diff = compute_diff(text, text)
        # Sem linhas adicionadas, o diff não deve ter "+"
        self.assertNotIn('+ Linha', diff)

    def test_detects_structured_cade_movements(self):
        # Cada célula da tabela HTML vira uma linha após o parse — simulamos isso aqui.
        old_text = 'Lista de Andamentos\nData/Hora\nUnidade\nDescricao'
        new_text = (
            'Lista de Andamentos\n'
            'Data/Hora\nUnidade\nDescricao\n'
            '01/07/2026 10:00\n'
            'SEAE\n'
            'Despacho de autuação'
        )
        summary, _ = compute_diff(old_text, new_text)
        # Com andamento detectado, deve mencionar andamento(s)
        self.assertIn('andamento', summary.lower())


class CheckRunServiceTest(TestCase):
    def setUp(self):
        self.process = MonitoredProcess.objects.create(
            label='Processo de Teste',
            source='https://sei.cade.gov.br/test',
            status=ProcessStatus.ACTIVE,
        )

    @patch('apps.monitoring.services.get_snapshot')
    def test_first_check_creates_baseline(self, mock_get_snapshot):
        from apps.monitoring.clients import Snapshot
        mock_get_snapshot.return_value = Snapshot(
            url='https://sei.cade.gov.br/test',
            status_code=200,
            title='Processo Teste',
            text='Conteúdo inicial do processo.',
            content_hash='hash_inicial_abc',
            fetched_at='2026-07-06T10:00:00+00:00',
            content_length=500,
            html='<html><body>Conteúdo inicial do processo.</body></html>',
        )
        from apps.monitoring.services import run_check
        result = run_check(self.process)

        self.assertTrue(result['ok'])
        self.assertFalse(result['changed'])
        self.process.refresh_from_db()
        self.assertEqual(self.process.last_hash, 'hash_inicial_abc')

    @patch('apps.monitoring.services.get_snapshot')
    def test_no_change_returns_ok_not_changed(self, mock_get_snapshot):
        from apps.monitoring.clients import Snapshot
        self.process.last_hash = 'hash_existente_xyz'
        self.process.last_text = 'Conteúdo atual'
        self.process.save()

        mock_get_snapshot.return_value = Snapshot(
            url='https://sei.cade.gov.br/test',
            status_code=200,
            title='Test',
            text='Conteúdo atual',
            content_hash='hash_existente_xyz',
            fetched_at='2026-07-06T10:00:00+00:00',
            content_length=200,
        )
        from apps.monitoring.services import run_check
        result = run_check(self.process)

        self.assertTrue(result['ok'])
        self.assertFalse(result['changed'])

    @patch('apps.monitoring.services.get_snapshot')
    def test_change_detected_creates_detected_change(self, mock_get_snapshot):
        from apps.monitoring.clients import Snapshot
        self.process.last_hash = 'hash_antigo'
        self.process.last_text = 'Conteúdo antigo'
        self.process.save()

        mock_get_snapshot.return_value = Snapshot(
            url='https://sei.cade.gov.br/test',
            status_code=200,
            title='Test',
            text='Conteúdo novo com mudança importante',
            content_hash='hash_novo',
            fetched_at='2026-07-06T10:00:00+00:00',
            content_length=300,
        )
        from apps.monitoring.models import DetectedChange
        from apps.monitoring.services import run_check

        result = run_check(self.process)

        self.assertTrue(result['ok'])
        self.assertTrue(result['changed'])
        self.assertEqual(DetectedChange.objects.filter(process=self.process).count(), 1)
