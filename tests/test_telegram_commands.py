"""
Testes dos comandos do bot (contracts/bot-commands.md), via services.handle_update.
Bot API mockada: as respostas são lidas das chamadas a client.send_message.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.monitoring.models import DetectedChange, PageSnapshot
from apps.processes.models import MonitoredProcess, ProcessOrigin, ProcessStatus
from apps.subscribers.models import ProcessSubscription
from apps.telegram_bot import services
from apps.telegram_bot.client import TelegramResult
from apps.telegram_bot.models import BotAction, BotActionKind, TelegramChat

from .telegram_helpers import OK, PROC, member_update, message_update, sent_texts, telegram_settings

BASELINE_TEXT = 'Lista de Andamentos\n06/07/2026 10:00\nSEAE\nDespacho publicado'


class CommandTestBase(TestCase):
    def setUp(self):
        patcher = patch('apps.telegram_bot.client.send_message', return_value=OK)
        self.mock_send = patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, text, **kwargs):
        self.mock_send.reset_mock()
        services.handle_update(message_update(text, **kwargs))
        texts = sent_texts(self.mock_send)
        return texts[-1] if texts else None

    def chat(self, chat_id=111):
        return TelegramChat.objects.get(chat_id=chat_id)

    def make_baseline_process(self, source=PROC, origin=ProcessOrigin.TELEGRAM):
        return MonitoredProcess.objects.create(
            label=source, source=source, origin=origin, status=ProcessStatus.ACTIVE,
            last_hash='h', last_text=BASELINE_TEXT, last_checked_at=timezone.now() - timedelta(hours=1),
        )


@telegram_settings
class StartAndHelpTest(CommandTestBase):
    def test_start_creates_chat_and_subscriber(self):
        text = self.send('/start')
        self.assertIn('CADE Monitor', text)
        chat = self.chat()
        self.assertEqual(chat.subscriber.name, 'Ana')
        self.assertFalse(chat.subscriber.email_enabled)

    def test_start_reactivates_unreachable_chat(self):
        self.send('/start')
        TelegramChat.objects.update(is_reachable=False)
        self.send('/start')
        self.assertTrue(self.chat().is_reachable)

    def test_free_text_and_unknown_command_get_help(self):
        self.assertIn('Não entendi', self.send('olá, bot'))
        self.assertIn('Não entendi', self.send('/foo'))

    def test_free_text_in_group_is_ignored(self):
        self.assertIsNone(self.send('bom dia', chat_id=-5, chat_type='group'))


@telegram_settings
class WatchTest(CommandTestBase):
    def test_new_process_queues_initial_read_without_scraping(self):
        with patch('apps.monitoring.clients.get_snapshot') as mock_fetch:
            text = self.send(f'/watch {PROC}')
        mock_fetch.assert_not_called()
        self.assertIn('Consultando', text)
        process = MonitoredProcess.objects.get(source=PROC)
        self.assertEqual(process.origin, ProcessOrigin.TELEGRAM)
        sub = ProcessSubscription.objects.get(process=process)
        self.assertTrue(sub.telegram_enabled)
        self.assertFalse(sub.email_enabled)
        self.assertTrue(BotAction.objects.filter(kind=BotActionKind.INITIAL_WATCH, process=process).exists())

    def test_known_process_answers_immediately(self):
        self.make_baseline_process()
        text = self.send('/watch 08700005905202638')
        self.assertIn('Pronto', text)
        self.assertIn('Despacho publicado', text)
        self.assertFalse(BotAction.objects.exists())

    def test_panel_process_suspended_by_admin_is_flagged(self):
        process = self.make_baseline_process(origin=ProcessOrigin.PANEL)
        process.status = ProcessStatus.PAUSED
        process.save()
        self.assertIn('suspenso pela administração', self.send(f'/watch {PROC}'))
        process.refresh_from_db()
        self.assertEqual(process.status, ProcessStatus.PAUSED)

    def test_validation_errors(self):
        self.assertIn('Informe o número', self.send('/watch'))
        self.assertIn('Número inválido', self.send('/watch 123'))
        self.assertFalse(MonitoredProcess.objects.exists())

    def test_duplicate(self):
        self.send(f'/watch {PROC}')
        self.assertIn('já acompanha', self.send(f'/watch {PROC}'))
        self.assertEqual(ProcessSubscription.objects.count(), 1)
        self.assertEqual(BotAction.objects.count(), 1)

    def test_limit_per_chat(self):
        for n in range(3):
            self.send(f'/watch 08700.00590{n}/2026-38')
        self.assertIn('limite', self.send('/watch 08700.009999/2026-38'))
        self.assertEqual(ProcessSubscription.objects.count(), 3)


@telegram_settings
class ManageTest(CommandTestBase):
    def setUp(self):
        super().setUp()
        self.process = self.make_baseline_process()
        self.send(f'/watch {PROC}')

    def test_list(self):
        self.assertIn(f'▶️ {PROC}', self.send('/list'))
        self.assertIn('ainda não acompanha', self.send('/list', chat_id=222))

    def test_status(self):
        text = self.send(f'/status {PROC}')
        self.assertIn('Última verificação', text)
        self.assertIn('Nenhuma mudança detectada', text)

    def test_history_respects_limit_and_order(self):
        snap = PageSnapshot.objects.create(process=self.process, content_hash='x', text_content='t')
        for n in range(3):
            change = DetectedChange.objects.create(
                process=self.process, new_snapshot=snap, new_hash='x', summary=f'mudança {n}', diff_text='',
            )
            DetectedChange.objects.filter(pk=change.pk).update(detected_at=timezone.now() - timedelta(days=3 - n))
        text = self.send(f'/history {PROC}')
        self.assertIn('mudança 2', text)
        self.assertIn('mudança 1', text)
        self.assertNotIn('mudança 0', text)
        self.assertLess(text.index('mudança 2'), text.index('mudança 1'))

    def test_other_chat_cannot_see_process(self):
        for cmd in ('status', 'history', 'check', 'pause', 'resume', 'unwatch'):
            with self.subTest(cmd=cmd):
                self.assertIn('não acompanha', self.send(f'/{cmd} {PROC}', chat_id=222))

    def test_pause_and_resume_manage_bot_process_status(self):
        self.assertIn('pausados', self.send(f'/pause {PROC}'))
        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatus.PAUSED)
        self.assertIn('⏸️', self.send('/list'))
        self.assertIn('retomados', self.send(f'/resume {PROC}'))
        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatus.ACTIVE)

    def test_pause_of_one_chat_keeps_process_active_for_others(self):
        self.send(f'/watch {PROC}', chat_id=222)
        self.send(f'/pause {PROC}')
        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatus.ACTIVE)

    def test_unwatch_pauses_orphan_bot_process_but_never_panel_process(self):
        self.assertIn('não acompanha mais', self.send(f'/unwatch {PROC}'))
        self.process.refresh_from_db()
        self.assertEqual(self.process.status, ProcessStatus.PAUSED)

        panel = self.make_baseline_process(source='08700.000001/2026-01', origin=ProcessOrigin.PANEL)
        self.send('/watch 08700.000001/2026-01')
        self.send('/unwatch 08700.000001/2026-01')
        panel.refresh_from_db()
        self.assertEqual(panel.status, ProcessStatus.ACTIVE)

    def test_check_within_cooldown_uses_saved_state(self):
        self.process.last_checked_at = timezone.now() - timedelta(seconds=60)
        self.process.save()
        text = self.send(f'/check {PROC}')
        self.assertIn('4 min', text)
        self.assertFalse(BotAction.objects.filter(kind=BotActionKind.CHECK).exists())

    def test_check_after_cooldown_queues_single_action(self):
        self.assertIn('Verificando', self.send(f'/check {PROC}'))
        self.send(f'/check {PROC}')
        self.assertEqual(BotAction.objects.filter(kind=BotActionKind.CHECK).count(), 1)


@telegram_settings
class GroupTest(CommandTestBase):
    GROUP = {'chat_id': -500, 'chat_type': 'group', 'title': 'Equipe'}

    def _member_status(self, status):
        return patch('apps.telegram_bot.client.get_chat_member',
                     return_value=TelegramResult(ok=True, result={'status': status}))

    def test_admin_can_manage(self):
        with self._member_status('administrator'):
            self.assertIn('Consultando', self.send(f'/watch {PROC}', **self.GROUP))
        self.assertTrue(self.chat(-500).is_group)

    def test_member_cannot_manage_but_can_read(self):
        with self._member_status('member'):
            for cmd in ('watch', 'unwatch', 'pause', 'resume'):
                with self.subTest(cmd=cmd):
                    self.assertIn('só administradores', self.send(f'/{cmd} {PROC}', **self.GROUP))
            self.assertIn('ainda não acompanha', self.send('/list', **self.GROUP))
        self.assertFalse(ProcessSubscription.objects.exists())

    def test_admin_check_failure_denies(self):
        with patch('apps.telegram_bot.client.get_chat_member',
                   return_value=TelegramResult(ok=False, error_code=400, description='x')):
            self.assertIn('Não consegui confirmar', self.send(f'/watch {PROC}', **self.GROUP))

    def test_commands_addressed_to_bots(self):
        self.assertIn('ainda não acompanha', self.send('/list@ExemploBot', **self.GROUP))
        self.assertIsNone(self.send('/list@OutroBot', **self.GROUP))

    def test_bot_removed_and_readded(self):
        self.send('/start', **self.GROUP)
        services.handle_update(member_update('kicked'))
        self.assertFalse(self.chat(-500).is_reachable)
        services.handle_update(member_update('member'))
        self.assertTrue(self.chat(-500).is_reachable)

    def test_user_blocking_bot_in_private(self):
        self.send('/start')
        services.handle_update(member_update('kicked', chat_id=111, chat_type='private'))
        self.assertFalse(self.chat().is_reachable)

    def test_supergroup_migration_keeps_subscriptions(self):
        with self._member_status('creator'):
            self.send(f'/watch {PROC}', **self.GROUP)
        services.handle_update(message_update('', migrate_to_chat_id=-100500, **self.GROUP))
        chat = self.chat(-100500)
        self.assertEqual(chat.chat_type, 'supergroup')
        self.assertEqual(chat.subscriber.subscriptions.count(), 1)
