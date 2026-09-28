from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.core import mail
from django.test import TestCase

from apps.agenda import services
from apps.agenda.models import CadeCalendarYear, ProcessInvite
from apps.agenda.tests.fixtures import load_fixture
from apps.monitoring.models import DetectedChange, PageSnapshot
from apps.processes.models import MonitoredProcess, ProcessStatus
from apps.subscribers.models import ProcessSubscription, Subscriber


def _attachment_content_type(email_message, index: int = 0) -> str:
    """O anexo `.ics` de convite/cancelamento é uma parte MIME construída à mão
    (email.mime.text.MIMEText, para poder usar `set_param('method', ...)`) —
    diferente do anexo (filename, content, mimetype) de outros canais."""
    return email_message.attachments[index]['Content-Type']


def _confirm_year(year: int) -> None:
    CadeCalendarYear.objects.create(year=year, status=CadeCalendarYear.Status.CONFIRMED)


def _make_process(fixture: str, **kwargs) -> MonitoredProcess:
    defaults = dict(
        label='AC Sumário de Teste', source=f'https://sei.cade.gov.br/{fixture}',
        status=ProcessStatus.ACTIVE, last_text=load_fixture(fixture),
    )
    defaults.update(kwargs)
    return MonitoredProcess.objects.create(**defaults)


def _subscribe(process: MonitoredProcess, email: str = 'assinante@example.com', **kwargs) -> ProcessSubscription:
    subscriber = Subscriber.objects.create(name='Assinante', email=email, email_enabled=True)
    defaults = dict(subscriber=subscriber, process=process, email_enabled=True, paused=False)
    defaults.update(kwargs)
    return ProcessSubscription.objects.create(**defaults)


class RefreshTimelinesAndInvitesTests(TestCase):
    def setUp(self):
        _confirm_year(2027)

    def test_first_analysis_deadline_sends_invite_with_ics_attachment(self):
        process = _make_process('ac_sumario_so_notificacao.txt')
        _subscribe(process)

        result = services.refresh_timelines_and_invites(datetime.now(dt_timezone.utc))

        self.assertEqual(result['sent'], 1)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(len(sent.attachments), 1)
        content_type = _attachment_content_type(sent)
        self.assertIn('text/calendar', content_type)
        self.assertIn('method="REQUEST"', content_type)
        self.assertTrue(
            ProcessInvite.objects.filter(
                process=process, deadline_type=ProcessInvite.DeadlineType.SG_ANALYSIS,
                status=ProcessInvite.Status.SENT, sequence=0,
            ).exists()
        )

    def test_no_change_does_not_resend(self):
        process = _make_process('ac_sumario_so_notificacao.txt')
        _subscribe(process)
        now = datetime.now(dt_timezone.utc)
        services.refresh_timelines_and_invites(now)
        mail.outbox.clear()

        services.refresh_timelines_and_invites(now)

        self.assertEqual(len(mail.outbox), 0)

    def test_deadline_fulfilled_sends_cancel(self):
        process = _make_process('ac_sumario_so_notificacao.txt')
        _subscribe(process)
        now = datetime.now(dt_timezone.utc)
        services.refresh_timelines_and_invites(now)
        mail.outbox.clear()

        process.last_text = load_fixture('ac_sumario_com_aprovacao.txt')
        process.save()
        services.refresh_timelines_and_invites(now)

        cancel_mails = [m for m in mail.outbox if 'method="CANCEL"' in _attachment_content_type(m)]
        self.assertEqual(len(cancel_mails), 1)
        invite = ProcessInvite.objects.get(process=process, deadline_type=ProcessInvite.DeadlineType.SG_ANALYSIS)
        self.assertEqual(invite.status, ProcessInvite.Status.CANCELLED)

    def test_estimated_certificate_date_change_sends_updated_request_with_incremented_sequence(self):
        process = _make_process('ac_sumario_com_aprovacao.txt')
        _subscribe(process)
        now = datetime.now(dt_timezone.utc)
        services.refresh_timelines_and_invites(now)
        certidao_invite = ProcessInvite.objects.get(
            process=process, deadline_type=ProcessInvite.DeadlineType.FINAL_CERTIFICATE,
        )
        self.assertEqual(certidao_invite.sequence, 0)
        mail.outbox.clear()

        # Aprovação republicada em data diferente muda a previsão da certidão.
        process.last_text = load_fixture('ac_sumario_com_aprovacao.txt').replace('26/01/2027', '02/02/2027')
        process.save()
        services.refresh_timelines_and_invites(now)

        certidao_invite.refresh_from_db()
        self.assertEqual(certidao_invite.sequence, 1)
        request_mails = [m for m in mail.outbox if 'method="REQUEST"' in _attachment_content_type(m)]
        self.assertTrue(request_mails)

    def test_subscriber_with_email_disabled_receives_nothing(self):
        process = _make_process('ac_sumario_so_notificacao.txt')
        _subscribe(process, email_enabled=False)

        services.refresh_timelines_and_invites(datetime.now(dt_timezone.utc))

        self.assertEqual(len(mail.outbox), 0)

    def test_paused_subscription_receives_nothing(self):
        process = _make_process('ac_sumario_so_notificacao.txt')
        _subscribe(process, paused=True)

        services.refresh_timelines_and_invites(datetime.now(dt_timezone.utc))

        self.assertEqual(len(mail.outbox), 0)


class RunAutoClosureTests(TestCase):
    """FR-017/FR-018: cada uma das 4 guardas testada isoladamente — só o cenário
    com as 4 passando apaga o processo (Acceptance Scenarios 1-6)."""

    def setUp(self):
        _confirm_year(2027)

    def _process_with_certidao(self, dias_desde_certidao: int, **overrides) -> MonitoredProcess:
        now = datetime.now(dt_timezone.utc)
        certidao_date = (now - timedelta(days=dias_desde_certidao)).date()
        last_text = load_fixture('ac_sumario_com_certidao.txt').replace(
            '16/02/2027', certidao_date.strftime('%d/%m/%Y'),
        )
        defaults = dict(
            label='AC Sumário', source='https://sei.cade.gov.br/x', status=ProcessStatus.ACTIVE,
            last_text=last_text, last_error='', last_checked_at=now,
        )
        defaults.update(overrides)
        return MonitoredProcess.objects.create(**defaults)

    def test_scenario_1_all_guards_pass_deletes_process(self):
        process = self._process_with_certidao(dias_desde_certidao=11)
        pk = process.pk

        with patch('apps.agenda.services.logger') as mock_logger:
            result = services.run_auto_closure(datetime.now(dt_timezone.utc))

        self.assertEqual(result['deleted'], 1)
        self.assertFalse(MonitoredProcess.objects.filter(pk=pk).exists())
        self.assertTrue(mock_logger.info.called)

    def test_scenario_2_within_window_does_not_delete(self):
        process = self._process_with_certidao(dias_desde_certidao=5)
        services.run_auto_closure(datetime.now(dt_timezone.utc))
        self.assertTrue(MonitoredProcess.objects.filter(pk=process.pk).exists())

    def test_scenario_3_recent_movement_resets_window(self):
        process = self._process_with_certidao(dias_desde_certidao=15)
        snapshot = PageSnapshot.objects.create(process=process, content_hash='h', text_content='t')
        change = DetectedChange.objects.create(
            process=process, new_snapshot=snapshot, new_hash='h', summary='Novo andamento', diff_text='',
        )
        # detected_at é auto_now_add; ajusta via update() para simular uma
        # movimentação de 3 dias atrás, posterior à certidão (15 dias atrás).
        DetectedChange.objects.filter(pk=change.pk).update(
            detected_at=datetime.now(dt_timezone.utc) - timedelta(days=3),
        )
        services.run_auto_closure(datetime.now(dt_timezone.utc))
        self.assertTrue(MonitoredProcess.objects.filter(pk=process.pk).exists())

    def test_scenario_4_last_check_had_error_blocks_deletion(self):
        process = self._process_with_certidao(dias_desde_certidao=15, last_error='timeout')
        services.run_auto_closure(datetime.now(dt_timezone.utc))
        self.assertTrue(MonitoredProcess.objects.filter(pk=process.pk).exists())

    def test_scenario_5_stale_last_check_blocks_deletion(self):
        stale = datetime.now(dt_timezone.utc) - timedelta(days=5)
        process = self._process_with_certidao(dias_desde_certidao=15, last_checked_at=stale)
        services.run_auto_closure(datetime.now(dt_timezone.utc))
        self.assertTrue(MonitoredProcess.objects.filter(pk=process.pk).exists())

    def test_scenario_6_low_confidence_certificate_blocks_deletion(self):
        # 'Certidão de Julgamento' não bate no matcher de trânsito em julgado
        # (confiança inexistente = sem certidão reconhecida = guarda falha).
        now = datetime.now(dt_timezone.utc)
        last_text = load_fixture('ac_sumario_com_certidao.txt').replace(
            'Certidão de Trânsito em Julgado', 'Certidão de Julgamento',
        )
        process = MonitoredProcess.objects.create(
            label='AC Sumário', source='https://sei.cade.gov.br/y', status=ProcessStatus.ACTIVE,
            last_text=last_text, last_error='', last_checked_at=now,
        )
        services.run_auto_closure(now)
        self.assertTrue(MonitoredProcess.objects.filter(pk=process.pk).exists())

    def test_pending_invite_gets_cancel_before_deletion(self):
        process = self._process_with_certidao(dias_desde_certidao=11)
        _subscribe(process)
        ProcessInvite.objects.create(
            process=process, deadline_type=ProcessInvite.DeadlineType.FINAL_CERTIFICATE,
            uid=f'ac-{process.pk}-final_certificate@cade-monitor', event_date=date(2027, 2, 16),
            sequence=0, status=ProcessInvite.Status.SENT, is_estimate=False,
        )
        pk = process.pk

        services.run_auto_closure(datetime.now(dt_timezone.utc))

        self.assertFalse(MonitoredProcess.objects.filter(pk=pk).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('method="CANCEL"', _attachment_content_type(mail.outbox[0]))

    def test_non_ac_sumario_or_no_certificate_is_a_noop(self):
        MonitoredProcess.objects.create(
            label='Ordinário', source='https://sei.cade.gov.br/z', status=ProcessStatus.ACTIVE,
            last_text=load_fixture('processo_ordinario.txt'), last_error='',
            last_checked_at=datetime.now(dt_timezone.utc),
        )
        result = services.run_auto_closure(datetime.now(dt_timezone.utc))
        self.assertEqual(result['deleted'], 0)


class SyncCalendarTests(TestCase):
    def test_never_raises_and_covers_current_and_next_year(self):
        with patch('apps.agenda.calendar_source.sync_calendar_year') as mocked:
            services.sync_calendar(datetime.now(dt_timezone.utc))
        years = {call.args[0] for call in mocked.call_args_list}
        current_year = datetime.now(dt_timezone.utc).year
        self.assertEqual(years, {current_year, current_year + 1})

    def test_exception_in_one_year_does_not_stop_the_other(self):
        with patch('apps.agenda.calendar_source.sync_calendar_year', side_effect=RuntimeError('boom')):
            services.sync_calendar(datetime.now(dt_timezone.utc))  # não deve levantar
