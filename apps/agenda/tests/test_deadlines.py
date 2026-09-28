from datetime import date

from django.test import TestCase

from apps.agenda import deadlines as dl
from apps.agenda.models import CadeCalendarEntry, CadeCalendarYear
from apps.agenda.tests.fixtures import load_fixture
from apps.monitoring.extractors import extract_protocol_records


def _confirm_year(year: int, holidays: list[tuple[date, str]] | None = None) -> CadeCalendarYear:
    record = CadeCalendarYear.objects.create(year=year, status=CadeCalendarYear.Status.CONFIRMED)
    for dia, nome in (holidays or []):
        CadeCalendarEntry.objects.create(calendar_year=record, date=dia, name=nome)
    return record


class CalculaPrazoCadeTests(TestCase):
    def setUp(self):
        # 2027-01-01 (sexta) é feriado; resto do calendário só tem fim de semana.
        # 2026 confirmado sem nenhum feriado de fim de ano, para testar a
        # travessia de virada de ano sem precisar de CalendarNotConfirmedError.
        _confirm_year(2026)
        _confirm_year(2027, [(date(2027, 1, 1), 'Ano Novo')])

    def test_preliminar_ja_e_dia_util_fica(self):
        # Evento numa segunda (2027-01-04) -> início = terça 01-05 (útil).
        # Vencimento preliminar = início + 9 dias = 01-14 (quinta, útil) -> fica.
        vencimento = dl.calcula_prazo_cade(date(2027, 1, 4), 10)
        self.assertEqual(vencimento, date(2027, 1, 14))

    def test_preliminar_cai_em_feriado_empurra_para_proximo_util(self):
        # Início = 2026-12-30 (quarta, útil). Preliminar = início + 2 dias = 2027-01-01
        # (feriado cadastrado) -> avança para 2027-01-02 (sábado) -> 2027-01-04 (segunda).
        vencimento = dl.calcula_prazo_cade(date(2026, 12, 29), 3)
        self.assertEqual(vencimento, date(2027, 1, 4))

    def test_evento_numa_sexta_antes_de_feriado_pula_corretamente(self):
        # Evento numa quinta (2026-12-31) -> início pula sexta 01-01 (feriado) e o
        # fim de semana, cai em 2027-01-04 (segunda).
        vencimento = dl.calcula_prazo_cade(date(2026, 12, 31), 1)
        self.assertEqual(vencimento, date(2027, 1, 4))

    def test_ano_do_calendario_nao_confirmado_levanta_erro_especifico(self):
        with self.assertRaises(dl.CalendarNotConfirmedError):
            dl.calcula_prazo_cade(date(2030, 1, 4), 10)


class ClassificaProcessoTests(TestCase):
    def test_reconhece_ac_sumario(self):
        for fixture in (
            'ac_sumario_so_notificacao.txt', 'ac_sumario_com_edital.txt',
            'ac_sumario_com_aprovacao.txt', 'ac_sumario_com_certidao.txt',
        ):
            with self.subTest(fixture=fixture):
                self.assertEqual(dl.classifica_processo(load_fixture(fixture)), 'ac_sumario')

    def test_processo_ordinario_nao_e_ac_sumario(self):
        self.assertIsNone(dl.classifica_processo(load_fixture('processo_ordinario.txt')))

    def test_lista_de_exclusao(self):
        for termo in ('Apuração de Ato Anticoncorrencial', 'Consulta', 'Recurso Voluntário'):
            texto = f'Tipo de Processo: Finalístico: {termo}\n'
            with self.subTest(termo=termo):
                self.assertIsNone(dl.classifica_processo(texto))


class DocumentMatcherTests(TestCase):
    def test_aprovacao_nao_confunde_despacho_decisorio_nem_ordinatorio(self):
        records = [
            {'doc_type': 'Despacho Decisório de Acesso Restrito', 'sort_key': '1', 'registry_date': '01/01/2027'},
            {'doc_type': 'Despacho Ordinatório', 'sort_key': '2', 'registry_date': '02/01/2027'},
        ]
        self.assertIsNone(dl.match_aprovacao(records))

    def test_aprovacao_reconhece_despacho_sg_explicito(self):
        records = [{'doc_type': 'Despacho SG de Aprovação', 'sort_key': '1', 'registry_date': '01/01/2027'}]
        match = dl.match_aprovacao(records)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(match.confidence, 0.8)

    def test_certidao_nao_confunde_certidao_de_julgamento(self):
        records = [{'doc_type': 'Certidão de Julgamento', 'sort_key': '1', 'registry_date': '01/01/2027'}]
        self.assertIsNone(dl.match_certidao(records))

    def test_certidao_reconhece_transito_em_julgado(self):
        records = [{'doc_type': 'Certidão de Trânsito em Julgado', 'sort_key': '1', 'registry_date': '01/01/2027'}]
        self.assertIsNotNone(dl.match_certidao(records))

    def test_notificacao_ignora_complementacao_e_recibo(self):
        records = [
            {'doc_type': 'Recibo de Notificação', 'sort_key': '1', 'registry_date': '01/01/2027'},
            {'doc_type': 'Complementação de Notificação', 'sort_key': '2', 'registry_date': '02/01/2027'},
            {'doc_type': 'Notificação de Ato de Concentração', 'sort_key': '3', 'registry_date': '03/01/2027'},
        ]
        match = dl.match_notificacao(records)
        self.assertEqual(match.record['sort_key'], '3')


class MontaLinhaDoTempoTests(TestCase):
    def setUp(self):
        _confirm_year(2027)

    def _process(self, fixture: str):
        class _Fake:
            last_text = load_fixture(fixture)
        return _Fake()

    def test_so_notificacao_mostra_so_prazo_de_analise(self):
        itens = dl.monta_linha_do_tempo(self._process('ac_sumario_so_notificacao.txt'))
        tipos = {item['tipo'] for item in itens}
        self.assertEqual(tipos, {'analise_sg'})
        records = extract_protocol_records(load_fixture('ac_sumario_so_notificacao.txt'))
        esperado = dl.calcula_prazo_cade(date(2027, 1, 4), 30)
        self.assertEqual(itens[0]['vencimento'], esperado)

    def test_com_edital_mostra_analise_e_terceiro_interessado(self):
        itens = dl.monta_linha_do_tempo(self._process('ac_sumario_com_edital.txt'))
        tipos = {item['tipo'] for item in itens}
        self.assertEqual(tipos, {'analise_sg', 'terceiro_interessado'})
        terceiro = next(i for i in itens if i['tipo'] == 'terceiro_interessado')
        self.assertEqual(terceiro['vencimento'], dl.calcula_prazo_cade(date(2027, 1, 12), 15))

    def test_com_aprovacao_analise_some_e_recurso_aparece(self):
        itens = dl.monta_linha_do_tempo(self._process('ac_sumario_com_aprovacao.txt'))
        tipos = {item['tipo'] for item in itens}
        self.assertNotIn('analise_sg', tipos)
        self.assertIn('recurso_avocacao', tipos)
        recurso = next(i for i in itens if i['tipo'] == 'recurso_avocacao')
        self.assertEqual(recurso['vencimento'], dl.calcula_prazo_cade(date(2027, 1, 26), 15))
        certidao = next(i for i in itens if i['tipo'] == 'certidao_final')
        self.assertTrue(certidao['estimado'])

    def test_com_certidao_real_nao_e_mais_estimativa(self):
        itens = dl.monta_linha_do_tempo(self._process('ac_sumario_com_certidao.txt'))
        certidao = next(i for i in itens if i['tipo'] == 'certidao_final')
        self.assertFalse(certidao['estimado'])
        self.assertEqual(certidao['vencimento'], date(2027, 2, 16))

    def test_processo_ordinario_linha_do_tempo_vazia(self):
        itens = dl.monta_linha_do_tempo(self._process('processo_ordinario.txt'))
        self.assertEqual(itens, [])

    def test_ano_nao_confirmado_prazo_fica_pendente_sem_excecao(self):
        class _Fake:
            last_text = (
                'Tipo de Processo: Finalístico: Ato de Concentração Sumário\n\n'
                'Lista de Protocolos\n'
                '1111111\nNotificação de Ato de Concentração\n04/01/2099\n04/01/2099\nSG\n'
            )
        itens = dl.monta_linha_do_tempo(_Fake())
        self.assertEqual(len(itens), 1)
        self.assertTrue(itens[0]['pendente'])
        self.assertIsNone(itens[0]['vencimento'])
