from unittest.mock import patch

from django.test import TestCase

from apps.monitoring.models import DetectedChange
from apps.monitoring.scheduler import get_due_processes
from apps.processes.models import MonitoredProcess
from apps.telegram_bot.demo import DEMO_PROCESS_SOURCE, RunDemoUseCase


class RunDemoUseCaseTests(TestCase):
    def test_response_has_all_required_elements(self):
        text = RunDemoUseCase().run()
        self.assertIn('Demonstração', text)
        self.assertIn('fictício', text)
        self.assertIn('Movimento anterior', text)
        self.assertIn('Nova movimentação', text)
        self.assertIn('Detectada em', text)
        self.assertIn('Resumo', text)
        self.assertIn('E-mail', text)
        self.assertIn('WhatsApp', text)
        self.assertIn('Telegram', text)

    def test_never_touches_network(self):
        # FR-006/SC-002: qualquer tentativa de abrir uma conexão real derruba o teste.
        with patch('urllib.request.urlopen', side_effect=AssertionError('rede real chamada')):
            text = RunDemoUseCase().run()
        self.assertIn('Demonstração', text)

    def test_never_sends_real_notification(self):
        # FR-007/SC-003: nenhum canal real de envio é alcançado.
        with (
            patch(
                'apps.notifications.channels.email.send_email_notification',
                side_effect=AssertionError('e-mail real chamado'),
            ),
            patch(
                'apps.notifications.channels.evolution.send_whatsapp_notification',
                side_effect=AssertionError('whatsapp real chamado'),
            ),
            patch('apps.telegram_bot.client.call', side_effect=AssertionError('telegram real chamado')),
            patch('apps.telegram_bot.client.send_message', side_effect=AssertionError('telegram real chamado')),
        ):
            text = RunDemoUseCase().run()
        self.assertIn('Demonstração', text)

    def test_idempotent_no_accumulation(self):
        # FR-002/SC-004: 5 chamadas seguidas nunca criam um segundo processo/mudança fictícios.
        for _ in range(5):
            RunDemoUseCase().run()
        self.assertEqual(MonitoredProcess.objects.filter(source=DEMO_PROCESS_SOURCE).count(), 1)
        self.assertEqual(DetectedChange.objects.filter(process__source=DEMO_PROCESS_SOURCE).count(), 1)

    def test_demo_process_never_due_for_real_check(self):
        # FR-008: status=ARCHIVED isola do ciclo real do worker.
        RunDemoUseCase().run()
        due_sources = [p.source for p in get_due_processes(100)]
        self.assertNotIn(DEMO_PROCESS_SOURCE, due_sources)
