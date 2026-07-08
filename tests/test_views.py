"""
Testes de views e formulários.
Usa o Django test Client para verificar respostas HTTP sem mock de rede.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from apps.monitoring.models import DetectedChange, CheckRun, PageSnapshot
from apps.processes.models import MonitoredProcess, ProcessStatus
from apps.subscribers.models import ProcessSubscription, Subscriber


def _make_process(**kwargs):
    defaults = {
        'label': 'Processo de Teste',
        'source': 'https://sei.cade.gov.br/test',
        'status': ProcessStatus.ACTIVE,
    }
    defaults.update(kwargs)
    return MonitoredProcess.objects.create(**defaults)


class AuthRedirectTest(TestCase):
    """Views protegidas devem redirecionar para login quando não autenticado."""

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_process_list_requires_login(self):
        response = self.client.get(reverse('processes:list'))
        self.assertEqual(response.status_code, 302)


class ProcessListViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'a@b.com', 'password')
        self.client.login(username='admin', password='password')
        _make_process(source='https://sei.cade.gov.br/p1', status=ProcessStatus.ACTIVE)
        _make_process(source='https://sei.cade.gov.br/p2', status=ProcessStatus.PAUSED)

    def test_list_returns_200(self):
        response = self.client.get(reverse('processes:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Processo de Teste')

    def test_filter_by_status_active(self):
        response = self.client.get(reverse('processes:list') + '?status=active')
        self.assertEqual(response.status_code, 200)
        # Apenas o processo ativo deve aparecer no contexto filtrado
        self.assertEqual(response.context['processes'].count(), 1)
        self.assertEqual(response.context['processes'].first().status, ProcessStatus.ACTIVE)

    def test_filter_by_status_paused(self):
        response = self.client.get(reverse('processes:list') + '?status=paused')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['processes'].count(), 1)

    def test_invalid_status_filter_returns_all(self):
        response = self.client.get(reverse('processes:list') + '?status=invalido')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['processes'].count(), 2)


class ProcessDetailViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'a@b.com', 'password')
        self.client.login(username='admin', password='password')
        self.process = _make_process()

    def test_detail_returns_200(self):
        url = reverse('processes:detail', kwargs={'pk': self.process.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.process.label)

    def test_detail_has_pagination_context(self):
        url = reverse('processes:detail', kwargs={'pk': self.process.pk})
        response = self.client.get(url)
        self.assertIn('page_obj', response.context)

    def test_detail_404_for_nonexistent(self):
        url = reverse('processes:detail', kwargs={'pk': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class ProcessCreateViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'a@b.com', 'password')
        self.client.login(username='admin', password='password')

    def test_get_create_form_returns_200(self):
        response = self.client.get(reverse('processes:create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cadastrar processo')

    def test_post_valid_url_creates_process(self):
        count_before = MonitoredProcess.objects.count()
        self.client.post(reverse('processes:create'), {
            'label': 'Novo Processo',
            'source': 'https://sei.cade.gov.br/novo',
            'check_interval_seconds': 1500,
            'status': 'active',
            'notes': '',
        })
        self.assertEqual(MonitoredProcess.objects.count(), count_before + 1)

    def test_post_invalid_scheme_rejected(self):
        response = self.client.post(reverse('processes:create'), {
            'label': 'Inválido',
            'source': 'ftp://sei.cade.gov.br/test',
            'check_interval_seconds': 1500,
            'status': 'active',
        })
        # Formulário inválido — deve renderizar o form novamente (200)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MonitoredProcess.objects.count(), 0)


class SSRFProtectionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'a@b.com', 'password')
        self.client.login(username='admin', password='password')

    def _post_source(self, source):
        return self.client.post(reverse('processes:create'), {
            'label': 'SSRF Test',
            'source': source,
            'check_interval_seconds': 1500,
            'status': 'active',
            'notes': '',
        })

    def test_localhost_rejected(self):
        response = self._post_source('http://localhost/admin')
        self.assertEqual(response.status_code, 200)  # form inválido, re-renderiza
        self.assertContains(response, 'rede interna')
        self.assertEqual(MonitoredProcess.objects.count(), 0)

    def test_loopback_ip_rejected(self):
        response = self._post_source('http://127.0.0.1/secret')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'rede interna')

    def test_private_ip_rejected(self):
        response = self._post_source('http://192.168.1.1/router')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'rede interna')

    def test_public_url_accepted(self):
        """URLs públicas reais devem passar na validação do formulário."""
        from apps.processes.forms import ProcessForm
        form = ProcessForm(data={
            'label': 'Teste CADE',
            'source': 'https://sei.cade.gov.br/test',
            'check_interval_seconds': 1500,
            'status': 'active',
            'notes': '',
        })
        # Apenas valida o campo source sem resolução DNS de rede externa
        # (host não existe no test env, mas a validação de schema deve passar)
        self.assertNotIn('rede interna', str(form.errors.get('source', [])))


class SubscriberViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'a@b.com', 'password')
        self.client.login(username='admin', password='password')
        self.subscriber = Subscriber.objects.create(
            name='João', email='joao@example.com', email_enabled=True
        )

    def test_subscriber_list_returns_200(self):
        response = self.client.get(reverse('subscribers:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'João')

    def test_subscriber_detail_returns_200(self):
        url = reverse('subscribers:detail', kwargs={'pk': self.subscriber.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_subscriber_create_get_returns_200(self):
        response = self.client.get(reverse('subscribers:create'))
        self.assertEqual(response.status_code, 200)


class NotificationActionsViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'a@b.com', 'password')
        self.client.login(username='admin', password='password')
        self.process = _make_process(source='https://sei.cade.gov.br/notif-test')

    @patch('apps.notifications.channels.email.send_email_notification')
    def test_send_test_email_success(self, send_email_notification):
        send_email_notification.return_value = ('sent', None)
        subscriber = Subscriber.objects.create(
            name='Email User',
            email='email.user@example.com',
            email_enabled=True,
        )
        ProcessSubscription.objects.create(
            subscriber=subscriber,
            process=self.process,
            email_enabled=True,
            whatsapp_enabled=False,
        )

        response = self.client.post(reverse('dashboard:send_test_email'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:notifications'))
        send_email_notification.assert_called_once()

    def test_send_test_email_without_destination(self):
        response = self.client.post(reverse('dashboard:send_test_email'), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nenhum assinante com e-mail habilitado foi encontrado para teste.')

    @patch('apps.notifications.channels.evolution.send_whatsapp_notification')
    def test_send_test_whatsapp_success(self, send_whatsapp_notification):
        send_whatsapp_notification.return_value = ('sent', None)
        subscriber = Subscriber.objects.create(
            name='WA User',
            phone='5511999998888',
            whatsapp_enabled=True,
        )
        ProcessSubscription.objects.create(
            subscriber=subscriber,
            process=self.process,
            email_enabled=False,
            whatsapp_enabled=True,
        )

        response = self.client.post(reverse('dashboard:send_test_whatsapp'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:notifications'))
        send_whatsapp_notification.assert_called_once()

    @patch('apps.notifications.channels.evolution.send_whatsapp_notification')
    def test_send_test_whatsapp_success_without_process_subscription_flag(self, send_whatsapp_notification):
        send_whatsapp_notification.return_value = ('sent', None)
        Subscriber.objects.create(
            name='WA Global',
            phone='5511912345678',
            whatsapp_enabled=True,
        )

        response = self.client.post(reverse('dashboard:send_test_whatsapp'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:notifications'))
        send_whatsapp_notification.assert_called_once_with(
            phone='5511912345678',
            body=(
                'CADE Monitor: esta e uma mensagem de teste enviada pela tela de notificacoes.\n\n'
                'Se chegou aqui, o canal WhatsApp esta funcionando.'
            ),
        )

    def test_send_test_whatsapp_without_destination(self):
        response = self.client.post(reverse('dashboard:send_test_whatsapp'), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nenhum assinante com WhatsApp habilitado foi encontrado para teste.')

    @patch('apps.notifications.channels.evolution.send_whatsapp_notification')
    def test_send_test_whatsapp_uses_only_enabled_subscribers(self, send_whatsapp_notification):
        send_whatsapp_notification.return_value = ('sent', None)
        wa_enabled = Subscriber.objects.create(
            name='WA On',
            phone='5511911111111',
            whatsapp_enabled=True,
        )
        wa_disabled = Subscriber.objects.create(
            name='WA Off',
            phone='5511922222222',
            whatsapp_enabled=False,
        )
        ProcessSubscription.objects.create(
            subscriber=wa_enabled,
            process=self.process,
            email_enabled=False,
            whatsapp_enabled=True,
        )
        ProcessSubscription.objects.create(
            subscriber=wa_disabled,
            process=self.process,
            email_enabled=False,
            whatsapp_enabled=True,
        )

        response = self.client.post(reverse('dashboard:send_test_whatsapp'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:notifications'))
        send_whatsapp_notification.assert_called_once_with(
            phone='5511911111111',
            body=(
                'CADE Monitor: esta e uma mensagem de teste enviada pela tela de notificacoes.\n\n'
                'Se chegou aqui, o canal WhatsApp esta funcionando.'
            ),
        )


class ProcessNotificationActionViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'a@b.com', 'password')
        self.client.login(username='admin', password='password')
        self.process = _make_process(source='https://sei.cade.gov.br/process-notify')

    @patch('apps.notifications.channels.evolution.send_whatsapp_notification')
    @patch('apps.notifications.channels.email.send_email_notification')
    def test_notify_subscribers_respects_channel_preferences(self, send_email_notification, send_whatsapp_notification):
        send_email_notification.return_value = ('sent', None)
        send_whatsapp_notification.return_value = ('sent', None)

        full = Subscriber.objects.create(
            name='Full',
            email='full@example.com',
            phone='5511933333333',
            email_enabled=True,
            whatsapp_enabled=True,
        )
        email_only = Subscriber.objects.create(
            name='Email Only',
            email='email.only@example.com',
            phone='5511944444444',
            email_enabled=True,
            whatsapp_enabled=True,
        )
        wa_global_off = Subscriber.objects.create(
            name='WA Global Off',
            email='wa.off@example.com',
            phone='5511955555555',
            email_enabled=True,
            whatsapp_enabled=False,
        )

        ProcessSubscription.objects.create(
            subscriber=full,
            process=self.process,
            email_enabled=True,
            whatsapp_enabled=True,
        )
        ProcessSubscription.objects.create(
            subscriber=email_only,
            process=self.process,
            email_enabled=True,
            whatsapp_enabled=False,
        )
        ProcessSubscription.objects.create(
            subscriber=wa_global_off,
            process=self.process,
            email_enabled=False,
            whatsapp_enabled=True,
        )

        response = self.client.post(
            reverse('processes:notify_subscribers', kwargs={'pk': self.process.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('processes:detail', kwargs={'pk': self.process.pk}),
        )
        self.assertEqual(send_email_notification.call_count, 2)
        self.assertEqual(send_whatsapp_notification.call_count, 1)

    @patch('apps.notifications.channels.evolution.send_whatsapp_notification')
    def test_process_test_whatsapp_sends_only_to_eligible_subscribers(self, send_whatsapp_notification):
        send_whatsapp_notification.return_value = ('sent', None)

        wa_enabled = Subscriber.objects.create(
            name='WA Enabled',
            phone='5511966666666',
            whatsapp_enabled=True,
        )
        wa_subscription_off = Subscriber.objects.create(
            name='WA Sub Off',
            phone='5511977777777',
            whatsapp_enabled=True,
        )
        wa_global_off = Subscriber.objects.create(
            name='WA Global Off',
            phone='5511988888888',
            whatsapp_enabled=False,
        )

        ProcessSubscription.objects.create(
            subscriber=wa_enabled,
            process=self.process,
            email_enabled=False,
            whatsapp_enabled=True,
        )
        ProcessSubscription.objects.create(
            subscriber=wa_subscription_off,
            process=self.process,
            email_enabled=False,
            whatsapp_enabled=False,
        )
        ProcessSubscription.objects.create(
            subscriber=wa_global_off,
            process=self.process,
            email_enabled=False,
            whatsapp_enabled=True,
        )

        response = self.client.post(
            reverse('processes:test_whatsapp', kwargs={'pk': self.process.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('processes:detail', kwargs={'pk': self.process.pk}),
        )
        self.assertEqual(send_whatsapp_notification.call_count, 2)
        called = {call.kwargs['phone']: call.kwargs['body'] for call in send_whatsapp_notification.call_args_list}
        self.assertIn('5511966666666', called)
        self.assertIn('5511977777777', called)

        for body in called.values():
            self.assertIn('🧪 *Teste de WhatsApp - CADE Monitor*', body)
            self.assertIn(f'📁 *Processo:* {self.process.label}', body)
            self.assertIn(f'🔗 *Link do processo:* {self.process.effective_url}', body)
            self.assertIn('🕒 *Ultima atualizacao:*', body)
