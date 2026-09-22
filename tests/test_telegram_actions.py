"""
Testes das ações do bot executadas pelo worker (actions.py).
Scraping mockado em lookup_process_url / run_check.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.monitoring.clients import FetchError
from apps.processes.models import MonitoredProcess, ProcessStatus
from apps.telegram_bot import services
from apps.telegram_bot.actions import FAST_RETRY_ATTEMPTS, process_pending_bot_actions
from apps.telegram_bot.models import BotAction, BotActionKind, BotActionStatus

from .telegram_helpers import OK, PROC, message_update, sent_texts, telegram_settings

DETAIL_URL = 'https://sei.cade.gov.br/sei/processo?id=1'
BASELINE_TEXT = 'Lista de Andamentos\n06/07/2026 10:00\nSEAE\nDespacho publicado'


def _fake_run_check(changed=False, ok=True):
    def run(process, notify_initial=False):
        if ok:
            MonitoredProcess.objects.filter(pk=process.pk).update(
                last_hash='h', last_text=BASELINE_TEXT, last_checked_at=timezone.now(),
                status=ProcessStatus.ACTIVE,
            )
        else:
            MonitoredProcess.objects.filter(pk=process.pk).update(
                last_checked_at=timezone.now(), status=ProcessStatus.ERROR, last_error='HTTP 503',
            )
        return {'ok': ok, 'changed': changed, 'message': ''}
    return run


@telegram_settings
class BotActionsTest(TestCase):
    def setUp(self):
        patcher = patch('apps.telegram_bot.client.send_message', return_value=OK)
        self.mock_send = patcher.start()
        self.addCleanup(patcher.stop)

    def watch(self, chat_id=111):
        services.handle_update(message_update(f'/watch {PROC}', chat_id=chat_id))
        self.mock_send.reset_mock()

    def run_actions(self):
        process_pending_bot_actions()
        return sent_texts(self.mock_send)

    @patch('apps.telegram_bot.actions.run_check', side_effect=_fake_run_check())
    @patch('apps.telegram_bot.actions.lookup_process_url', return_value=DETAIL_URL)
    def test_first_read_success_then_sends_latest_update(self, mock_lookup, mock_run):
        self.watch()
        texts = self.run_actions()
        self.assertEqual(len(texts), 2)
        self.assertIn('Pronto', texts[0])
        self.assertIn('Última atualização', texts[1])
        process = MonitoredProcess.objects.get(source=PROC)
        self.assertEqual(process.resolved_url, DETAIL_URL)
        self.assertEqual(BotAction.objects.get().status, BotActionStatus.DONE)

    @patch('apps.telegram_bot.actions.run_check', side_effect=_fake_run_check())
    @patch('apps.telegram_bot.actions.lookup_process_url', return_value=DETAIL_URL)
    def test_two_chats_same_process_single_fetch(self, mock_lookup, mock_run):
        self.watch(111)
        self.watch(222)
        texts = self.run_actions()
        self.assertEqual(mock_run.call_count, 1)
        self.assertEqual(len(texts), 4)  # confirmação + última atualização, para cada chat

    @patch('apps.telegram_bot.actions.run_check')
    @patch('apps.telegram_bot.actions.lookup_process_url', return_value=None)
    def test_not_found_cancels_and_removes_orphan(self, mock_lookup, mock_run):
        self.watch()
        texts = self.run_actions()
        self.assertIn('Não encontrei', texts[0])
        mock_run.assert_not_called()
        self.assertFalse(MonitoredProcess.objects.filter(source=PROC).exists())

    @patch('apps.telegram_bot.actions.lookup_process_url', side_effect=FetchError('Falha de rede'))
    def test_network_failure_retries_then_falls_back_to_normal_cadence(self, mock_lookup):
        self.watch()
        action = BotAction.objects.get()
        messages_sent = []
        for _ in range(FAST_RETRY_ATTEMPTS):
            BotAction.objects.filter(pk=action.pk).update(next_attempt_at=timezone.now())
            messages_sent += self.run_actions()
            self.mock_send.reset_mock()
        action.refresh_from_db()
        self.assertEqual(action.status, BotActionStatus.PENDING)  # nunca expira sozinha
        self.assertEqual(action.attempts, FAST_RETRY_ATTEMPTS)
        self.assertGreater(action.next_attempt_at, timezone.now() + timedelta(minutes=20))
        self.assertEqual(len(messages_sent), 2)  # "vou tentar de novo" + "rotina normal"
        self.assertIn('não respondeu', messages_sent[0])

    def test_not_due_actions_are_skipped(self):
        self.watch()
        BotAction.objects.update(next_attempt_at=timezone.now() + timedelta(minutes=5))
        with patch('apps.telegram_bot.actions.lookup_process_url') as mock_lookup:
            self.run_actions()
        mock_lookup.assert_not_called()

    def test_baseline_created_meanwhile_answers_without_fetch(self):
        self.watch()
        MonitoredProcess.objects.filter(source=PROC).update(last_hash='h', last_text=BASELINE_TEXT)
        with patch('apps.telegram_bot.actions.run_check') as mock_run:
            texts = self.run_actions()
        mock_run.assert_not_called()
        self.assertIn('Pronto', texts[0])


@telegram_settings
class CheckActionsTest(TestCase):
    def setUp(self):
        patcher = patch('apps.telegram_bot.client.send_message', return_value=OK)
        self.mock_send = patcher.start()
        self.addCleanup(patcher.stop)
        MonitoredProcess.objects.create(
            label=PROC, source=PROC, resolved_url=DETAIL_URL, status=ProcessStatus.ACTIVE,
            last_hash='h', last_text=BASELINE_TEXT, last_checked_at=timezone.now() - timedelta(hours=1),
        )
        for chat_id in (111, 222):
            services.handle_update(message_update(f'/watch {PROC}', chat_id=chat_id))
            services.handle_update(message_update(f'/check {PROC}', chat_id=chat_id))
        # Estes testes cobrem só o /check: descarta a última atualização disparada pelo /watch.
        BotAction.objects.filter(kind=BotActionKind.LATEST).delete()
        self.mock_send.reset_mock()

    def test_no_change(self):
        with patch('apps.telegram_bot.actions.run_check', side_effect=_fake_run_check()) as mock_run:
            process_pending_bot_actions()
        texts = sent_texts(self.mock_send)
        self.assertEqual(mock_run.call_count, 1)
        self.assertEqual(len(texts), 2)
        self.assertTrue(all('Sem novidades' in t for t in texts))

    def test_change_points_to_regular_alert(self):
        with patch('apps.telegram_bot.actions.run_check', side_effect=_fake_run_check(changed=True)):
            process_pending_bot_actions()
        self.assertTrue(all('alerta a seguir' in t for t in sent_texts(self.mock_send)))

    def test_failure(self):
        with patch('apps.telegram_bot.actions.run_check', side_effect=_fake_run_check(ok=False)):
            process_pending_bot_actions()
        self.assertTrue(all('Não consegui consultar' in t for t in sent_texts(self.mock_send)))
        self.assertEqual(set(BotAction.objects.values_list('status', flat=True)), {BotActionStatus.FAILED})

    def test_recently_checked_by_schedule_answers_without_fetch(self):
        MonitoredProcess.objects.update(last_checked_at=timezone.now())
        with patch('apps.telegram_bot.actions.run_check') as mock_run:
            process_pending_bot_actions()
        mock_run.assert_not_called()
        self.assertEqual(len(sent_texts(self.mock_send)), 2)
