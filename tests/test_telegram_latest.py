"""
Testes do /ultima (última atualização com documento) e do PDF nos alertas do Telegram.
SEI e Bot API sempre mockados.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.monitoring.clients import FetchError
from apps.monitoring.models import DetectedChange, DetectedDocument, PageSnapshot
from apps.notifications.models import NotificationChannel, NotificationStatus
from apps.notifications.services import create_notifications_for_change, dispatch_notification
from apps.processes.models import MonitoredProcess, ProcessStatus
from apps.telegram_bot import services
from apps.telegram_bot.actions import process_pending_bot_actions
from apps.telegram_bot.client import TelegramResult
from apps.telegram_bot.models import BotAction, BotActionKind, BotActionStatus

from .telegram_helpers import OK, PROC, message_update, sent_texts, telegram_settings

PROTOCOL_TEXT = (
    'Lista de Protocolos\nProcesso / Documento\nTipo\nData\nData de Registro\nUnidade\n'
    '1234567\nParecer\n01/09/2026\n02/09/2026\nCGAA1\n'
    '7654321\nNota Técnica\n10/09/2026\n11/09/2026\nSG\n'
)
DOC_URL = 'https://sei.cade.gov.br/sei/documento?id=7654321'
PDF = {'content': b'%PDF-1.4', 'filename': '7654321-Nota_Tecnica.pdf', 'content_type': 'application/pdf'}


def _snapshot(url=DOC_URL):
    class Snap:
        html = f'<a href="{url}">7654321</a>'
        text = PROTOCOL_TEXT
    Snap.url = 'https://sei.cade.gov.br/processo'
    return Snap()


@telegram_settings
class UltimaCommandTest(TestCase):
    def setUp(self):
        patcher = patch('apps.telegram_bot.client.send_message', return_value=OK)
        self.mock_send = patcher.start()
        self.addCleanup(patcher.stop)
        doc_patcher = patch('apps.telegram_bot.client.send_document_file', return_value=OK)
        self.mock_doc = doc_patcher.start()
        self.addCleanup(doc_patcher.stop)
        self.process = MonitoredProcess.objects.create(
            label=PROC, source=PROC, status=ProcessStatus.ACTIVE, resolved_url='https://sei.cade.gov.br/processo',
            last_hash='h', last_text=PROTOCOL_TEXT, last_checked_at=timezone.now() - timedelta(hours=1),
        )

    def send(self, text, **kwargs):
        self.mock_send.reset_mock()
        services.handle_update(message_update(text, **kwargs))
        return sent_texts(self.mock_send)[-1]

    def test_queues_action_without_touching_sei(self):
        self.send(f'/watch {PROC}')
        with patch('apps.telegram_bot.actions.download_document') as mock_download:
            self.assertIn('Preparando a última atualização', self.send(f'/ultima {PROC}'))
        mock_download.assert_not_called()
        self.assertTrue(BotAction.objects.filter(kind=BotActionKind.LATEST).exists())

    def test_requires_subscription_and_baseline(self):
        self.assertIn('não acompanha', self.send(f'/ultima {PROC}'))
        MonitoredProcess.objects.filter(pk=self.process.pk).update(last_hash='')
        self.send(f'/watch {PROC}')
        self.assertIn('Ainda não tenho a primeira leitura', self.send(f'/ultima {PROC}'))

    def test_group_members_can_use_it(self):
        with patch('apps.telegram_bot.client.get_chat_member',
                   return_value=TelegramResult(ok=True, result={'status': 'administrator'})):
            self.send(f'/watch {PROC}', chat_id=-9, chat_type='group')
        with patch('apps.telegram_bot.client.get_chat_member',
                   return_value=TelegramResult(ok=True, result={'status': 'member'})) as mock_member:
            self.assertIn('Preparando', self.send(f'/ultima {PROC}', chat_id=-9, chat_type='group'))
        mock_member.assert_not_called()

    @patch('apps.telegram_bot.actions.get_snapshot')
    @patch('apps.telegram_bot.actions.download_document', return_value=PDF)
    def test_worker_sends_text_and_uploads_known_document(self, mock_download, mock_page):
        snap = PageSnapshot.objects.create(process=self.process, content_hash='h', text_content=PROTOCOL_TEXT)
        change = DetectedChange.objects.create(
            process=self.process, new_snapshot=snap, new_hash='h', summary='Nota técnica juntada.', diff_text='',
        )
        DetectedDocument.objects.create(change=change, document_number='7654321', title='Nota Técnica', url=DOC_URL)
        self.send(f'/watch {PROC}')
        self.send(f'/ultima {PROC}')
        self.mock_send.reset_mock()

        process_pending_bot_actions()

        text = sent_texts(self.mock_send)[0]
        self.assertIn('7654321 | Nota Técnica | 10/09/2026', text)  # o mais recente, não o 1234567
        self.assertIn(DOC_URL, text)
        self.assertIn('Nota técnica juntada.', text)
        self.assertIn('Documento em anexo', text)
        mock_page.assert_not_called()  # link já conhecido: não consulta a página
        self.assertEqual(mock_download.call_args.kwargs['url'], DOC_URL)
        self.mock_doc.assert_called_once_with(111, b'%PDF-1.4', PDF['filename'], 'application/pdf')
        self.assertEqual(BotAction.objects.get(kind=BotActionKind.LATEST).status, BotActionStatus.DONE)

    @patch('apps.telegram_bot.actions.extract_document_links', return_value={'7654321': DOC_URL})
    @patch('apps.telegram_bot.actions.get_snapshot', return_value=_snapshot())
    @patch('apps.telegram_bot.actions.download_document', return_value=PDF)
    def test_unknown_link_is_looked_up_on_process_page_once_for_all_chats(self, mock_download, mock_page, _links):
        for chat_id in (111, 222):
            self.send(f'/watch {PROC}', chat_id=chat_id)
            self.send(f'/ultima {PROC}', chat_id=chat_id)

        process_pending_bot_actions()

        self.assertEqual(mock_page.call_count, 1)
        self.assertEqual(mock_download.call_count, 1)
        self.assertEqual(self.mock_doc.call_count, 2)

    @patch('apps.telegram_bot.actions.extract_document_links', return_value={'7654321': DOC_URL})
    @patch('apps.telegram_bot.actions.get_snapshot', return_value=_snapshot())
    @patch('apps.telegram_bot.actions.download_document', side_effect=FetchError('HTTP 503'))
    def test_download_failure_still_sends_text_with_link(self, _mock_download, _mock_page, _links):
        self.send(f'/watch {PROC}')
        self.send(f'/ultima {PROC}')
        self.mock_send.reset_mock()
        process_pending_bot_actions()
        text = sent_texts(self.mock_send)[0]
        self.assertIn('Não consegui baixar o documento', text)
        self.assertIn(DOC_URL, text)
        self.mock_doc.assert_not_called()


@telegram_settings
class TelegramAlertAttachmentTest(TestCase):
    """Alertas de mudança: o PDF é baixado e enviado por upload (não por URL)."""

    def setUp(self):
        from apps.subscribers.models import ProcessSubscription, Subscriber
        from apps.telegram_bot.models import TelegramChat

        self.process = MonitoredProcess.objects.create(label='P', source='https://sei.cade.gov.br/p')
        subscriber = Subscriber.objects.create(name='Ana', email_enabled=False, whatsapp_enabled=False)
        TelegramChat.objects.create(chat_id=42, chat_type='private', title='Ana', subscriber=subscriber)
        ProcessSubscription.objects.create(
            subscriber=subscriber, process=self.process,
            email_enabled=False, whatsapp_enabled=False, telegram_enabled=True,
        )
        snap = PageSnapshot.objects.create(process=self.process, content_hash='h', text_content='t')
        self.change = DetectedChange.objects.create(
            process=self.process, new_snapshot=snap, new_hash='h', summary='s', diff_text='',
        )
        DetectedDocument.objects.create(change=self.change, document_number='7654321', title='Nota', url=DOC_URL)

    @patch('apps.telegram_bot.client.send_document_file', return_value=OK)
    @patch('apps.telegram_bot.client.send_message', return_value=OK)
    @patch('apps.notifications.services.download_document', return_value=PDF)
    def test_alert_downloads_and_uploads_document(self, mock_download, _mock_msg, mock_upload):
        notification = create_notifications_for_change(self.change)[0]
        self.assertEqual(notification.channel, NotificationChannel.TELEGRAM)
        self.assertEqual(dispatch_notification(notification), NotificationStatus.SENT)
        self.assertEqual(mock_download.call_args.kwargs['url'], DOC_URL)
        mock_upload.assert_called_once_with('42', b'%PDF-1.4', PDF['filename'], 'application/pdf')

    @patch('apps.telegram_bot.client.send_document_file')
    @patch('apps.telegram_bot.client.send_message', return_value=OK)
    @patch('apps.notifications.services.download_document', side_effect=FetchError('HTTP 503'))
    def test_download_failure_keeps_document_pending_for_retry(self, _mock_download, _mock_msg, mock_upload):
        notification = create_notifications_for_change(self.change)[0]
        dispatch_notification(notification)
        mock_upload.assert_not_called()
        state = notification.document_states.get()
        self.assertEqual(state.status, 'pending')
