"""
Testes do app notifications.
Testa criação de notificações e despacho para canais.
"""
from unittest.mock import patch

from django.test import TestCase

from apps.monitoring.models import CheckRun, DetectedChange, PageSnapshot
from apps.notifications.models import Notification, NotificationChannel, NotificationStatus
from apps.notifications.services import create_notifications_for_change, dispatch_notification
from apps.monitoring.models import DetectedDocument
from apps.notifications.models import NotificationDocumentState, NotificationDocumentStatus
from apps.processes.models import MonitoredProcess, ProcessStatus
from apps.subscribers.models import ProcessSubscription, Subscriber


def _make_process(label='Processo Teste', source='https://sei.cade.gov.br/test'):
    return MonitoredProcess.objects.create(
        label=label,
        source=source,
        status=ProcessStatus.ACTIVE,
    )


def _make_change(process):
    run = CheckRun.objects.create(process=process, status='changed')
    snap = PageSnapshot.objects.create(
        process=process,
        content_hash='abc123def456',
        text_content='Novo conteúdo detectado',
    )
    return DetectedChange.objects.create(
        process=process,
        check_run=run,
        new_snapshot=snap,
        new_hash='abc123def456',
        summary='2 novos andamentos detectados.',
        diff_text='+ Novo andamento: 06/07/2026 10:00 | SEAE | Despacho',
    )


class CreateNotificationsTest(TestCase):
    def test_creates_email_notification(self):
        process = _make_process()
        subscriber = Subscriber.objects.create(
            name='João da Silva',
            email='joao@example.com',
            email_enabled=True,
            whatsapp_enabled=False,
        )
        ProcessSubscription.objects.create(
            subscriber=subscriber,
            process=process,
            email_enabled=True,
            whatsapp_enabled=False,
        )

        change = _make_change(process)
        notifications = create_notifications_for_change(change)

        self.assertEqual(len(notifications), 1)
        n = notifications[0]
        self.assertEqual(n.channel, NotificationChannel.EMAIL)
        self.assertEqual(n.destination, 'joao@example.com')
        self.assertEqual(n.status, NotificationStatus.PENDING)

    def test_silent_subscriber_receives_nothing(self):
        process = _make_process(source='https://sei.cade.gov.br/test2')
        subscriber = Subscriber.objects.create(
            name='Silencioso',
            email='silent@example.com',
            email_enabled=True,
            silent_mode=True,
        )
        ProcessSubscription.objects.create(
            subscriber=subscriber, process=process, email_enabled=True,
        )
        change = _make_change(process)
        notifications = create_notifications_for_change(change)
        self.assertEqual(len(notifications), 0)

    def test_whatsapp_not_created_when_evolution_disabled(self):
        process = _make_process(source='https://sei.cade.gov.br/test3')
        subscriber = Subscriber.objects.create(
            name='WA User',
            phone='5511999998888',
            whatsapp_enabled=True,
        )
        ProcessSubscription.objects.create(
            subscriber=subscriber, process=process,
            email_enabled=False, whatsapp_enabled=True,
        )
        change = _make_change(process)

        # Garante que EVOLUTION_ENABLED=False
        with self.settings(EVOLUTION_ENABLED=False):
            notifications = create_notifications_for_change(change)

        whatsapp_notifications = [n for n in notifications if n.channel == NotificationChannel.WHATSAPP]
        self.assertEqual(len(whatsapp_notifications), 0)

    def test_paused_subscriber_receives_nothing(self):
        from django.utils import timezone
        from datetime import timedelta

        process = _make_process(source='https://sei.cade.gov.br/test4')
        subscriber = Subscriber.objects.create(
            name='Pausado',
            email='paused@example.com',
            email_enabled=True,
            paused_until=timezone.now() + timedelta(days=7),
        )
        ProcessSubscription.objects.create(
            subscriber=subscriber, process=process, email_enabled=True,
        )
        change = _make_change(process)
        notifications = create_notifications_for_change(change)
        self.assertEqual(len(notifications), 0)


class EvolutionChannelTest(TestCase):
    def test_returns_not_configured_when_disabled(self):
        from apps.notifications.channels.evolution import send_whatsapp_notification
        with self.settings(EVOLUTION_ENABLED=False):
            status, error = send_whatsapp_notification('5511999998888', 'Teste')
        self.assertEqual(status, 'channel_not_configured')

    def test_returns_invalid_recipient_for_bad_phone(self):
        from apps.notifications.channels.evolution import send_whatsapp_notification
        with self.settings(EVOLUTION_ENABLED=True, EVOLUTION_API_BASE_URL='http://localhost', EVOLUTION_API_KEY='key'):
            status, error = send_whatsapp_notification('abc-invalido', 'Teste')
        self.assertEqual(status, 'invalid_recipient')


class NotificationAttachmentsFlowTest(TestCase):
    def setUp(self):
        self.process = _make_process(source='https://sei.cade.gov.br/test-attachments')
        self.subscriber = Subscriber.objects.create(
            name='Anexo User',
            email='anexo@example.com',
            email_enabled=True,
            whatsapp_enabled=False,
        )
        ProcessSubscription.objects.create(
            subscriber=self.subscriber,
            process=self.process,
            email_enabled=True,
            whatsapp_enabled=False,
        )
        self.change = _make_change(self.process)

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.notifications.services.download_document')
    def test_partial_attachment_failure_does_not_block_email(self, mock_download_document, mock_send_email):
        doc_ok = DetectedDocument.objects.create(
            change=self.change,
            document_number='100001',
            title='Ofício',
            url='https://sei.cade.gov.br/doc/100001.pdf',
            mode='attachment',
            status='pending_retry',
            retryable=True,
        )
        doc_fail = DetectedDocument.objects.create(
            change=self.change,
            document_number='100002',
            title='Laudo',
            url='https://sei.cade.gov.br/doc/100002.pdf',
            mode='attachment',
            status='pending_retry',
            retryable=True,
        )

        def _download_side_effect(url, record, timeout, user_agent, max_bytes=None):
            if '100001' in url:
                return {
                    'document': '100001',
                    'title': 'Ofício',
                    'filename': '100001-oficio.pdf',
                    'content_type': 'application/pdf',
                    'content': b'pdf-content',
                    'url': url,
                }
            from apps.monitoring.clients import FetchError
            raise FetchError('Documento indisponível no momento')

        mock_download_document.side_effect = _download_side_effect
        mock_send_email.return_value = (NotificationStatus.SENT, None)

        notifications = create_notifications_for_change(self.change)
        self.assertEqual(len(notifications), 1)
        notification = notifications[0]

        status = dispatch_notification(notification)
        notification.refresh_from_db()

        self.assertEqual(status, NotificationStatus.PENDING)
        self.assertIsNotNone(notification.sent_at)
        mock_send_email.assert_called_once()
        attachments = mock_send_email.call_args.kwargs['attachments']
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]['document'], '100001')

        state_ok = NotificationDocumentState.objects.get(notification=notification, document=doc_ok)
        state_fail = NotificationDocumentState.objects.get(notification=notification, document=doc_fail)
        self.assertEqual(state_ok.status, NotificationDocumentStatus.SENT)
        self.assertEqual(state_fail.status, NotificationDocumentStatus.PENDING)

    @patch('apps.notifications.channels.email.send_email_notification')
    def test_zip_document_is_link_only_and_marked_sent(self, mock_send_email):
        doc_zip = DetectedDocument.objects.create(
            change=self.change,
            document_number='200001',
            title='Anexo compactado ZIP',
            url='https://sei.cade.gov.br/doc/200001.zip',
            mode='link_only',
            status='link_only_notified',
            retryable=False,
            failure_reason='Arquivo compactado (zip/rar/7z).',
        )
        mock_send_email.return_value = (NotificationStatus.SENT, None)

        notification = create_notifications_for_change(self.change)[0]
        result = dispatch_notification(notification)

        self.assertIn(result, (NotificationStatus.SENT, NotificationStatus.PENDING))
        state = NotificationDocumentState.objects.get(notification=notification, document=doc_zip)
        self.assertEqual(state.status, NotificationDocumentStatus.SENT)
