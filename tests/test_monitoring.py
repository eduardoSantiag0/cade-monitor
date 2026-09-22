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
    new_movement_records,
    normalize_text,
    related_process_mentions,
    relevant_movement_records,
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


class RelevantMovementTest(TestCase):
    def test_detects_related_process_mentions(self):
        text = 'Novo andamento: 01/07/2026 10:00 | SG | Documento movido para autos apartados 08700.123456/2026-11'
        mentions = related_process_mentions(text)
        self.assertIn('08700.123456/2026-11', mentions)

    def test_filters_only_relevant_movements(self):
        old_text = 'Lista de Andamentos\nData/Hora\nUnidade\nDescricao'
        new_text = (
            'Lista de Andamentos\n'
            'Data/Hora\nUnidade\nDescricao\n'
            '01/07/2026 10:00\nSG\nMovido para autos apartados 08700.123456/2026-11\n'
            '01/07/2026 11:00\nSG\nAtualização de rotina administrativa'
        )
        new_movements = new_movement_records(old_text, new_text)
        relevant = relevant_movement_records(new_movements)

        self.assertEqual(len(new_movements), 2)
        self.assertEqual(len(relevant), 1)
        self.assertIn('apartados', relevant[0]['text'].lower())


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
        from apps.monitoring.models import CheckRun
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
        self.assertEqual(CheckRun.objects.filter(process=self.process).count(), 0)

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

    @patch('apps.monitoring.services.get_snapshot')
    def test_invalid_page_is_not_accepted_as_change(self, mock_get_snapshot):
        from apps.monitoring.clients import Snapshot
        from apps.monitoring.models import DetectedChange

        self.process.last_hash = 'hash_antigo_xpto'
        self.process.last_text = (
            'Lista de Andamentos\n' + ('Linha válida\n' * 120) +
            'Lista de Protocolos\n' + ('Outro conteúdo\n' * 120)
        )
        self.process.save()

        mock_get_snapshot.return_value = Snapshot(
            url='https://sei.cade.gov.br/test',
            status_code=200,
            title='Access Denied',
            text='captcha bloqueado access denied',
            content_hash='hash_novo_invalido',
            fetched_at='2026-07-11T10:00:00+00:00',
            content_length=120,
            html='<html><body>captcha</body></html>',
        )

        from apps.monitoring.services import run_check
        result = run_check(self.process)

        self.assertFalse(result['ok'])
        self.assertFalse(result['changed'])
        self.assertIn('inválida', result['message'].lower())
        self.assertEqual(DetectedChange.objects.filter(process=self.process).count(), 0)
        self.process.refresh_from_db()
        self.assertEqual(self.process.last_hash, 'hash_antigo_xpto')


class RedisCacheFallbackTest(TestCase):
    """
    A Constituição do projeto (v1.1.0) permite Redis como cache opcional de
    hash de processo, sob a condição de que a aplicação continue funcional
    com o cache desabilitado. Estes testes provam essa condição diretamente
    em run_check, sem depender de um servidor Redis disponível
    (spec 002-repo-hardening-cleanup, FR-011).
    """

    def setUp(self):
        self.process = MonitoredProcess.objects.create(
            label='Processo sem Redis',
            source='https://sei.cade.gov.br/test-no-redis',
            status=ProcessStatus.ACTIVE,
        )

    @patch('apps.monitoring.services.get_snapshot')
    def test_no_change_detected_via_database_hash_without_redis(self, mock_get_snapshot):
        from apps.monitoring.clients import Snapshot
        from apps.monitoring.models import CheckRun
        from apps.monitoring.services import run_check

        self.process.last_hash = 'hash_estavel_sem_redis'
        self.process.last_text = 'Conteúdo estável'
        self.process.save()

        mock_get_snapshot.return_value = Snapshot(
            url='https://sei.cade.gov.br/test-no-redis',
            status_code=200,
            title='Test',
            text='Conteúdo estável',
            content_hash='hash_estavel_sem_redis',
            fetched_at='2026-09-22T10:00:00+00:00',
            content_length=200,
        )

        with self.settings(PROCESS_HASH_REDIS_ENABLED=False):
            result = run_check(self.process)

        self.assertTrue(result['ok'])
        self.assertFalse(result['changed'])
        # Sem Redis, a decisão de "sem mudança" só pode ter vindo do hash no banco.
        self.assertEqual(CheckRun.objects.filter(process=self.process).count(), 0)

    @patch('apps.monitoring.services.get_snapshot')
    def test_change_detected_via_database_hash_without_redis(self, mock_get_snapshot):
        from apps.monitoring.clients import Snapshot
        from apps.monitoring.models import DetectedChange
        from apps.monitoring.services import run_check

        self.process.last_hash = 'hash_anterior_sem_redis'
        self.process.last_text = 'Conteúdo anterior'
        self.process.save()

        mock_get_snapshot.return_value = Snapshot(
            url='https://sei.cade.gov.br/test-no-redis',
            status_code=200,
            title='Test',
            text='Conteúdo novo detectado sem cache',
            content_hash='hash_novo_sem_redis',
            fetched_at='2026-09-22T10:00:00+00:00',
            content_length=300,
        )

        with self.settings(PROCESS_HASH_REDIS_ENABLED=False):
            result = run_check(self.process)

        self.assertTrue(result['ok'])
        self.assertTrue(result['changed'])
        self.assertEqual(DetectedChange.objects.filter(process=self.process).count(), 1)
        self.process.refresh_from_db()
        self.assertEqual(self.process.last_hash, 'hash_novo_sem_redis')


class PostgresPortabilityTest(TestCase):
    """Comportamentos que diferem entre SQLite e Postgres (spec 005, research R8)."""

    def test_never_checked_processes_come_first(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.monitoring.scheduler import get_due_processes

        old = MonitoredProcess.objects.create(
            label='Antigo', source='https://a.example', status=ProcessStatus.ACTIVE,
            last_checked_at=timezone.now() - timedelta(days=2),
        )
        never = MonitoredProcess.objects.create(
            label='Nunca', source='https://b.example', status=ProcessStatus.ACTIVE,
        )
        self.assertEqual([p.pk for p in get_due_processes()], [never.pk, old.pk])
        self.assertEqual([p.pk for p in get_due_processes(limit=1)], [never.pk])

    def test_long_document_number_is_truncated(self):
        from apps.monitoring.models import DetectedChange, DetectedDocument, PageSnapshot
        from apps.monitoring.services import _persist_detected_documents

        process = MonitoredProcess.objects.create(label='P', source='https://p.example')
        snapshot = PageSnapshot.objects.create(process=process, content_hash='h', text_content='t')
        change = DetectedChange.objects.create(
            process=process, new_snapshot=snapshot, new_hash='h', summary='s', diff_text='d',
        )
        _persist_detected_documents(change, [{'document': '9' * 300, 'title': 'Nota'}])
        self.assertEqual(len(DetectedDocument.objects.get(change=change).document_number), 120)


class RunWorkerConnectionTest(TestCase):
    @patch('apps.monitoring.scheduler.get_due_processes', return_value=[])
    @patch('apps.monitoring.management.commands.run_worker.close_old_connections')
    def test_cycle_recycles_db_connections(self, mock_close, _mock_due):
        from django.core.management import call_command

        call_command('run_worker', '--once', stdout=MagicMock())
        mock_close.assert_called()

    @patch('apps.monitoring.scheduler.get_due_processes', side_effect=RuntimeError('db caiu'))
    @patch('apps.monitoring.management.commands.run_worker.close_old_connections')
    def test_failed_cycle_drops_connection_for_next_cycle(self, mock_close, _mock_due):
        from django.core.management import call_command

        call_command('run_worker', '--once', stdout=MagicMock())
        # uma no início do ciclo + uma no tratamento do erro
        self.assertEqual(mock_close.call_count, 2)
