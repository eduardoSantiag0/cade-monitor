from datetime import time as dt_time
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.dou.models import DouAnticipation, DouFetchState, DouSendLog, DouSubscription
from apps.dou.services import _should_fetch, run_anticipation_window, run_confirmation_window, run_digest_window
from apps.dou.tests.fixtures import load_fixture
from apps.monitoring.clients import FetchError
from apps.subscribers.models import Subscriber


class ShouldFetchTest(TestCase):
    @override_settings(DOU_FETCH_MIN_INTERVAL_SECONDS=300)
    def test_blocks_within_min_interval_and_allows_after(self):
        now = timezone.now()
        self.assertTrue(_should_fetch('resenha', now))
        self.assertFalse(_should_fetch('resenha', now + timedelta(seconds=60)))
        self.assertTrue(_should_fetch('resenha', now + timedelta(seconds=301)))

    @override_settings(DOU_FETCH_MIN_INTERVAL_SECONDS=300)
    def test_sources_do_not_compete(self):
        now = timezone.now()
        self.assertTrue(_should_fetch('resenha', now))
        self.assertTrue(_should_fetch('ingov_listing', now))

    def test_first_call_persists_state(self):
        now = timezone.now()
        _should_fetch('resenha', now)
        state = DouFetchState.objects.get(source='resenha')
        self.assertEqual(state.last_attempt_at, now)


@override_settings(DOU_DIGEST_WINDOW_START='00:00', DOU_DIGEST_WINDOW_END='23:59')
class RunDigestWindowTest(TestCase):
    def setUp(self):
        subscriber = Subscriber.objects.create(name='Fulano', email='fulano@example.com')
        self.subscription = DouSubscription.objects.create(subscriber=subscriber)
        self.resenha_html = load_fixture('resenha_com_publicacoes.json')['html']
        self.ingov_htmls = load_fixture('ingov_listing_com_publicacoes.json')['htmls']

    @override_settings(DOU_DIGEST_WINDOW_START='23:58', DOU_DIGEST_WINDOW_END='23:59')
    @patch('apps.dou.clients.fetch_resenha')
    def test_outside_window_skips_without_http(self, mock_fetch_resenha):
        result = run_digest_window(timezone.now())
        self.assertTrue(result['skipped'])
        mock_fetch_resenha.assert_not_called()

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_resenha')
    def test_sends_one_email_per_subscriber_and_logs(self, mock_fetch_resenha, mock_send):
        mock_fetch_resenha.return_value = {'source': 'resenha', 'html': self.resenha_html}
        mock_send.return_value = ('sent', None)
        result = run_digest_window(timezone.now())
        self.assertEqual(result['sent'], 1)
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(
            DouSendLog.objects.filter(subscription=self.subscription, kind=DouSendLog.Kind.DIGEST).count(), 1
        )

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_resenha')
    def test_second_call_same_day_does_not_resend(self, mock_fetch_resenha, mock_send):
        mock_fetch_resenha.return_value = {'source': 'resenha', 'html': self.resenha_html}
        mock_send.return_value = ('sent', None)
        now = timezone.now()
        run_digest_window(now)
        run_digest_window(now + timedelta(minutes=10))
        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(
            DouSendLog.objects.filter(subscription=self.subscription, kind=DouSendLog.Kind.DIGEST).count(), 1
        )

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_ingov_listing')
    @patch('apps.dou.clients.fetch_resenha')
    def test_falls_back_to_ingov_when_resenha_unavailable(self, mock_fetch_resenha, mock_fetch_listing, mock_send):
        mock_fetch_resenha.return_value = None
        mock_fetch_listing.return_value = {'source': 'ingov_listing', 'htmls': self.ingov_htmls}
        mock_send.return_value = ('sent', None)
        result = run_digest_window(timezone.now())
        self.assertEqual(result['sent'], 1)
        mock_fetch_listing.assert_called_once()

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_resenha')
    def test_silent_subscriber_is_skipped(self, mock_fetch_resenha, mock_send):
        self.subscription.subscriber.silent_mode = True
        self.subscription.subscriber.save()
        mock_fetch_resenha.return_value = {'source': 'resenha', 'html': self.resenha_html}
        mock_send.return_value = ('sent', None)
        result = run_digest_window(timezone.now())
        self.assertEqual(result['sent'], 0)
        mock_send.assert_not_called()


from datetime import datetime as dt  # noqa: E402


def _local_dt(*args):
    return timezone.make_aware(dt(*args))


@override_settings(DOU_ANTICIPATION_CUTOFF='22:00')
class RunAnticipationWindowTest(TestCase):
    def setUp(self):
        subscriber = Subscriber.objects.create(name='Fulano', email='fulano@example.com')
        self.subscription = DouSubscription.objects.create(
            subscriber=subscriber, nextday_enabled=True, nextday_time=dt_time(19, 30),
        )
        self.two_items_html = load_fixture('sei_boletim_dois_andamentos.json')['html']
        self.three_items_html = load_fixture('sei_boletim_um_andamento_novo.json')['html']
        self.after_due_time = _local_dt(2026, 7, 14, 20, 0)

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_sei_publications')
    def test_first_send_has_all_items_and_persists_anticipation(self, mock_fetch, mock_send):
        mock_fetch.return_value = {'source': 'sei_publications', 'html': self.two_items_html}
        mock_send.return_value = ('sent', None)
        result = run_anticipation_window(self.after_due_time)
        self.assertEqual(result['sent'], 1)
        anticipation = DouAnticipation.objects.get(subscription=self.subscription)
        self.assertEqual(len(anticipation.items), 2)
        self.assertEqual(
            DouSendLog.objects.filter(kind=DouSendLog.Kind.PUBDOU_ANT).count(), 1
        )

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_sei_publications')
    def test_complement_sends_only_new_item(self, mock_fetch, mock_send):
        mock_fetch.return_value = {'source': 'sei_publications', 'html': self.two_items_html}
        mock_send.return_value = ('sent', None)
        run_anticipation_window(self.after_due_time)

        mock_fetch.return_value = {'source': 'sei_publications', 'html': self.three_items_html}
        result = run_anticipation_window(self.after_due_time + timedelta(minutes=30))
        self.assertEqual(result['sent'], 1)
        self.assertEqual(mock_send.call_count, 2)
        last_html = mock_send.call_args_list[-1].args[2]
        self.assertIn('08700.007700/2026-03', last_html)
        self.assertNotIn('08700.009900/2026-01', last_html)
        anticipation = DouAnticipation.objects.get(subscription=self.subscription)
        self.assertEqual(len(anticipation.items), 3)

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_sei_publications')
    def test_no_items_sends_empty_notice(self, mock_fetch, mock_send):
        mock_fetch.return_value = {'source': 'sei_publications', 'html': '<div></div>'}
        mock_send.return_value = ('sent', None)
        result = run_anticipation_window(self.after_due_time)
        self.assertEqual(result['sent'], 1)
        html = mock_send.call_args.args[2]
        self.assertIn('Não tivemos publicações previstas', html)

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_sei_publications')
    def test_disabled_subscriber_never_receives_anticipation(self, mock_fetch, mock_send):
        self.subscription.nextday_enabled = False
        self.subscription.save()
        mock_fetch.return_value = {'source': 'sei_publications', 'html': self.two_items_html}
        result = run_anticipation_window(self.after_due_time)
        self.assertEqual(result, {'skipped': True, 'reason': 'no_subscribers', 'sent': 0, 'failed': 0})
        mock_send.assert_not_called()

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_sei_publications')
    def test_second_call_without_new_items_does_not_resend(self, mock_fetch, mock_send):
        mock_fetch.return_value = {'source': 'sei_publications', 'html': self.two_items_html}
        mock_send.return_value = ('sent', None)
        run_anticipation_window(self.after_due_time)
        run_anticipation_window(self.after_due_time + timedelta(minutes=30))
        self.assertEqual(mock_send.call_count, 1)

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_sei_publications')
    def test_silent_subscriber_skipped(self, mock_fetch, mock_send):
        self.subscription.subscriber.silent_mode = True
        self.subscription.subscriber.save()
        mock_fetch.return_value = {'source': 'sei_publications', 'html': self.two_items_html}
        run_anticipation_window(self.after_due_time)
        mock_send.assert_not_called()

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_sei_publications')
    def test_after_cutoff_sends_nothing(self, mock_fetch, mock_send):
        after_cutoff = _local_dt(2026, 7, 14, 23, 0)
        result = run_anticipation_window(after_cutoff)
        self.assertTrue(result['skipped'])
        mock_fetch.assert_not_called()
        mock_send.assert_not_called()


def _item(number, label):
    return {'titulo': f'Processo Administrativo nº {number}', 'text': f'Processo Administrativo nº {number} {label}', 'url': ''}


def _resenha_html(despacho_texts: list[str]) -> str:
    body = ''.join(f'<div>{d}</div>' for d in despacho_texts)
    return (
        '<div><strong>Seção 1</strong></div>'
        '<div><strong>CONSELHO ADMINISTRATIVO DE DEFESA ECONÔMICA</strong></div>'
        f'{body}'
    )


@override_settings(DOU_CONFIRMATION_WINDOW_START='00:00', DOU_CONFIRMATION_WINDOW_END='23:59')
class RunConfirmationWindowTest(TestCase):
    def setUp(self):
        subscriber = Subscriber.objects.create(name='Fulano', email='fulano@example.com')
        self.subscription = DouSubscription.objects.create(subscriber=subscriber, nextday_enabled=True)
        self.today = timezone.now()

    def _anticipate(self, items):
        return DouAnticipation.objects.create(
            subscription=self.subscription, reference_date=timezone.localdate(self.today), items=items,
        )

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_resenha')
    def test_all_confirmed(self, mock_fetch, mock_send):
        items = [_item('08700.000001/2026-01', 'A'), _item('08700.000002/2026-02', 'B'), _item('08700.000003/2026-03', 'C')]
        self._anticipate(items)
        mock_fetch.return_value = {'source': 'resenha', 'html': _resenha_html([
            'Processo Administrativo nº 08700.000001/2026-01 real A',
            'Processo Administrativo nº 08700.000002/2026-02 real B',
            'Processo Administrativo nº 08700.000003/2026-03 real C',
        ])}
        mock_send.return_value = ('sent', None)
        result = run_confirmation_window(self.today)
        self.assertEqual(result['sent'], 1)
        html = mock_send.call_args.args[2]
        self.assertIn('todos os andamentos abaixo', html)
        self.assertNotIn('exceto', html)

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_resenha')
    def test_one_missing_is_named_in_exceto(self, mock_fetch, mock_send):
        items = [_item('08700.000001/2026-01', 'A'), _item('08700.000002/2026-02', 'B')]
        self._anticipate(items)
        mock_fetch.return_value = {'source': 'resenha', 'html': _resenha_html([
            'Processo Administrativo nº 08700.000001/2026-01 real A',
        ])}
        mock_send.return_value = ('sent', None)
        run_confirmation_window(self.today)
        html = mock_send.call_args.args[2]
        self.assertIn('exceto', html)
        self.assertIn('08700.000002/2026-02', html)

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_resenha')
    def test_single_item_not_published_uses_singular(self, mock_fetch, mock_send):
        self._anticipate([_item('08700.000001/2026-01', 'A')])
        mock_fetch.return_value = {'source': 'resenha', 'html': _resenha_html([
            'Processo Administrativo nº 08700.999999/2026-99 outro assunto não relacionado',
        ])}
        mock_send.return_value = ('sent', None)
        run_confirmation_window(self.today)
        html = mock_send.call_args.args[2]
        self.assertIn('o andamento abaixo foi devidamente publicado', html)

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_resenha')
    def test_nothing_published_uses_special_notice(self, mock_fetch, mock_send):
        self._anticipate([_item('08700.000001/2026-01', 'A')])
        mock_fetch.return_value = {'source': 'resenha', 'html': _resenha_html([])}
        mock_send.return_value = ('sent', None)
        run_confirmation_window(self.today)
        html = mock_send.call_args.args[2]
        self.assertIn('Não tivemos publicações no DOU de hoje', html)
        self.assertNotIn('todos os andamentos', html)

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_resenha')
    def test_no_anticipation_no_confirmation(self, mock_fetch, mock_send):
        result = run_confirmation_window(self.today)
        self.assertTrue(result['skipped'])
        mock_send.assert_not_called()

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_resenha')
    def test_second_call_same_day_does_not_resend(self, mock_fetch, mock_send):
        self._anticipate([_item('08700.000001/2026-01', 'A')])
        mock_fetch.return_value = {'source': 'resenha', 'html': _resenha_html([
            'Processo Administrativo nº 08700.000001/2026-01 real A',
        ])}
        mock_send.return_value = ('sent', None)
        run_confirmation_window(self.today)
        run_confirmation_window(self.today + timedelta(minutes=10))
        self.assertEqual(mock_send.call_count, 1)

    @patch('apps.notifications.channels.email.send_email_notification')
    @patch('apps.dou.clients.fetch_resenha')
    def test_paused_subscriber_gets_no_confirmation(self, mock_fetch, mock_send):
        self.subscription.subscriber.paused_until = self.today + timedelta(days=1)
        self.subscription.subscriber.save()
        self._anticipate([_item('08700.000001/2026-01', 'A')])
        mock_fetch.return_value = {'source': 'resenha', 'html': _resenha_html([
            'Processo Administrativo nº 08700.000001/2026-01 real A',
        ])}
        run_confirmation_window(self.today)
        mock_send.assert_not_called()
