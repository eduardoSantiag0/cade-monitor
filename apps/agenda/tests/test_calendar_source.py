import re
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.agenda import calendar_source as cs
from apps.agenda.models import CadeCalendarEntry, CadeCalendarYear
from apps.agenda.tests.fixtures import load_fixture

VALID_ITEM = {
    'title': 'Portaria MGI Nº 123, de 20 de dezembro de 2026',
    'hierarchyStr': 'Ministério da Gestão e da Inovação em Serviços Públicos',
    'pubName': 'DO1',
}


class ExtractEntriesTests(TestCase):
    def test_extracts_dates_and_names_from_valid_fixture(self):
        texto = load_fixture('portaria_feriados_2027.txt')
        entradas = cs._extrai_entradas_portaria(texto, 2027)
        self.assertEqual(len(entradas), 13)
        self.assertIn((date(2027, 1, 1), 'Confraternização Universal'), entradas)
        self.assertIn((date(2027, 12, 25), 'Natal'), entradas)


class ValidatePortariaTests(TestCase):
    def _entradas(self, texto, ano=2027):
        return cs._extrai_entradas_portaria(texto, ano)

    def test_valid_fixture_passes(self):
        texto = load_fixture('portaria_feriados_2027.txt')
        ok, motivo = cs._valida_portaria(VALID_ITEM, texto, 2027, self._entradas(texto))
        self.assertTrue(ok, motivo)

    def test_rejects_too_few_dates(self):
        texto = load_fixture('portaria_invalida.txt')
        ok, motivo = cs._valida_portaria(VALID_ITEM, texto, 2027, self._entradas(texto))
        self.assertFalse(ok)
        self.assertIn('data(s) extraída(s)', motivo)

    def test_rejects_wrong_title(self):
        texto = load_fixture('portaria_feriados_2027.txt')
        item = {**VALID_ITEM, 'title': 'Resolução MGI nº 1'}
        ok, motivo = cs._valida_portaria(item, texto, 2027, self._entradas(texto))
        self.assertFalse(ok)
        self.assertIn('portaria', motivo)

    def test_rejects_wrong_orgao(self):
        texto = load_fixture('portaria_feriados_2027.txt')
        item = {**VALID_ITEM, 'hierarchyStr': 'Ministério da Agricultura'}
        ok, motivo = cs._valida_portaria(item, texto, 2027, self._entradas(texto))
        self.assertFalse(ok)
        self.assertIn('Órgão emissor', motivo)

    def test_rejects_wrong_secao(self):
        texto = load_fixture('portaria_feriados_2027.txt')
        item = {**VALID_ITEM, 'pubName': 'DO3'}
        ok, motivo = cs._valida_portaria(item, texto, 2027, self._entradas(texto))
        self.assertFalse(ok)
        self.assertIn('Seção 1', motivo)

    def test_rejects_missing_apf_scope(self):
        # Normaliza espaços (como `_texto_limpo` já faz em produção) antes de
        # remover a frase de escopo — a frase quebra em duas linhas no fixture.
        bruto = re.sub(r'\s+', ' ', load_fixture('portaria_feriados_2027.txt'))
        texto = bruto.replace('Administração Pública Federal direta, autárquica e fundacional', 'nada')
        self.assertNotIn('fundacional', texto)
        ok, motivo = cs._valida_portaria(VALID_ITEM, texto, 2027, self._entradas(texto))
        self.assertFalse(ok)
        self.assertIn('escopo da APF', motivo)

    def test_rejects_wrong_year_reference(self):
        texto = load_fixture('portaria_feriados_2027.txt').replace('2027', '2099')
        entradas = cs._extrai_entradas_portaria(load_fixture('portaria_feriados_2027.txt'), 2027)
        ok, motivo = cs._valida_portaria(VALID_ITEM, texto, 2027, entradas)
        self.assertFalse(ok)
        self.assertIn('não se refere ao ano', motivo)

    def test_rejects_revoked_act(self):
        texto = 'Ato revogado. ' + load_fixture('portaria_feriados_2027.txt')
        ok, motivo = cs._valida_portaria(VALID_ITEM, texto, 2027, self._entradas(texto))
        self.assertFalse(ok)
        self.assertIn('revogado', motivo)

    def test_rejects_dates_outside_target_year(self):
        texto = load_fixture('portaria_feriados_2027.txt')
        entradas = self._entradas(texto) + [(date(2028, 1, 1), 'Fora do ano')]
        ok, motivo = cs._valida_portaria(VALID_ITEM, texto, 2027, entradas)
        self.assertFalse(ok)
        self.assertIn('fora do ano-alvo', motivo)


class SyncCalendarYearTests(TestCase):
    def test_success_persists_confirmed_year_and_entries(self):
        texto = load_fixture('portaria_feriados_2027.txt')
        with patch('apps.agenda.calendar_source.busca_dou', return_value=[VALID_ITEM]), \
             patch('apps.agenda.calendar_source.texto_integral_dou', return_value=texto):
            cs.sync_calendar_year(2027, timeout=10, user_agent='test')

        record = CadeCalendarYear.objects.get(year=2027)
        self.assertEqual(record.status, CadeCalendarYear.Status.CONFIRMED)
        self.assertEqual(CadeCalendarEntry.objects.filter(calendar_year=record).count(), 13)
        self.assertIsNotNone(record.next_check_at)
        self.assertGreater(record.next_check_at, timezone.now() + timedelta(days=20))

    def test_respects_cadence_gate(self):
        future = timezone.now() + timedelta(days=1)
        CadeCalendarYear.objects.create(year=2027, next_check_at=future)
        with patch('apps.agenda.calendar_source.busca_dou') as mocked:
            cs.sync_calendar_year(2027, timeout=10, user_agent='test')
        mocked.assert_not_called()

    def test_network_failure_never_raises_and_reschedules(self):
        from apps.monitoring.clients import FetchError
        with patch('apps.agenda.calendar_source.busca_dou', side_effect=FetchError('boom')):
            cs.sync_calendar_year(2027, timeout=10, user_agent='test')
        record = CadeCalendarYear.objects.get(year=2027)
        self.assertEqual(record.status, CadeCalendarYear.Status.PENDING)
        self.assertIsNotNone(record.next_check_at)


class IsBusinessDayTests(TestCase):
    def setUp(self):
        year = CadeCalendarYear.objects.create(year=2027, status=CadeCalendarYear.Status.CONFIRMED)
        CadeCalendarEntry.objects.create(calendar_year=year, date=date(2027, 1, 1), name='Ano Novo')

    def test_weekend_is_not_business_day(self):
        # 2027-01-02 é sábado.
        self.assertFalse(cs.is_business_day(date(2027, 1, 2)))

    def test_holiday_is_not_business_day(self):
        self.assertFalse(cs.is_business_day(date(2027, 1, 1)))

    def test_regular_day_is_business_day(self):
        # 2027-01-04 é segunda-feira, sem feriado cadastrado.
        self.assertTrue(cs.is_business_day(date(2027, 1, 4)))

    def test_unconfirmed_year_never_raises(self):
        self.assertTrue(cs.is_business_day(date(2030, 1, 4)))
