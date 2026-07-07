"""
Testes do app processes.
Testa models, services e selectors — sem dependências externas.
"""
from django.test import TestCase

from apps.processes.models import MonitoredProcess, ProcessStatus
from apps.processes.selectors import get_active_processes, get_all_processes


class MonitoredProcessModelTest(TestCase):
    def setUp(self):
        self.process = MonitoredProcess.objects.create(
            label='Processo Teste',
            source='https://sei.cade.gov.br/test',
            status=ProcessStatus.ACTIVE,
        )

    def test_str_uses_label(self):
        self.assertEqual(str(self.process), 'Processo Teste')

    def test_effective_url_with_resolved(self):
        self.process.resolved_url = 'https://sei.cade.gov.br/resolved'
        self.assertEqual(self.process.effective_url, 'https://sei.cade.gov.br/resolved')

    def test_effective_url_fallback_to_source(self):
        self.process.resolved_url = ''
        self.assertEqual(self.process.effective_url, 'https://sei.cade.gov.br/test')

    def test_is_active(self):
        self.assertTrue(self.process.is_active)
        self.process.status = ProcessStatus.PAUSED
        self.assertFalse(self.process.is_active)

    def test_has_baseline_false_when_no_hash(self):
        self.assertFalse(self.process.has_baseline)

    def test_has_baseline_true_when_hash_set(self):
        self.process.last_hash = 'abc123'
        self.assertTrue(self.process.has_baseline)


class ProcessSelectorsTest(TestCase):
    def setUp(self):
        MonitoredProcess.objects.create(label='A', source='https://a.com', status=ProcessStatus.ACTIVE)
        MonitoredProcess.objects.create(label='B', source='https://b.com', status=ProcessStatus.PAUSED)
        MonitoredProcess.objects.create(label='C', source='https://c.com', status=ProcessStatus.ERROR)

    def test_get_all_processes_returns_all(self):
        self.assertEqual(get_all_processes().count(), 3)

    def test_get_active_processes_returns_only_active(self):
        active = get_active_processes()
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().label, 'A')
