from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.precedentes import services
from apps.precedentes.models import PrecedentCase


class CaseListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('advogado', password='senha123')

    def test_lista_exige_autenticacao(self):
        response = self.client.get(reverse('precedentes:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)

    def test_lista_mostra_casos_existentes(self):
        services.create_case(self.user, 'Caso Visível')
        self.client.force_login(self.user)
        response = self.client.get(reverse('precedentes:list'))
        self.assertContains(response, 'Caso Visível')

    def test_criar_caso_via_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('precedentes:case_create'), {'titulo': 'Novo Caso', 'cliente': '', 'notas': ''})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PrecedentCase.objects.filter(titulo='Novo Caso').exists())


class EntityViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('advogado', password='senha123')
        self.client.force_login(self.user)
        self.case = services.create_case(self.user, 'Caso')

    def test_editar_empresa_via_post(self):
        entity = services.add_entity(self.case, 'outro', 'Nome Antigo')
        response = self.client.post(
            reverse('precedentes:entity_update', args=[entity.pk]),
            {'papel': 'requerente', 'razao_social': 'Nome Novo', 'cnpj': '', 'pais': 'Brasil'},
        )
        self.assertEqual(response.status_code, 302)
        entity.refresh_from_db()
        self.assertEqual(entity.razao_social, 'Nome Novo')


class FactDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('advogado', password='senha123')
        self.client.force_login(self.user)
        self.case = services.create_case(self.user, 'Caso')
        self.entity = services.add_entity(self.case, 'requerente', 'Empresa X')

    def test_pagina_do_caso_agrupa_fatos_por_status_com_destaque(self):
        services.record_fact(
            self.entity, self.user, campo='faturamento', valor='100', status='confirmado', fonte_descricao='f',
        )
        services.record_fact(
            self.entity, self.user, campo='controladora', valor='desconhecida', status='solicitar_cliente',
        )
        response = self.client.get(reverse('precedentes:case_detail', args=[self.case.pk]))
        content = response.content.decode()
        self.assertIn('badge-confirmado', content)
        self.assertIn('badge-solicitar_cliente', content)

    def test_fatos_e_analises_tem_marcadores_visuais_distintos(self):
        fact = services.record_fact(
            self.entity, self.user, campo='faturamento', valor='100', status='confirmado', fonte_descricao='f',
        )
        services.record_analysis(self.case, self.user, 'Nota interpretativa', [fact])
        response = self.client.get(reverse('precedentes:case_detail', args=[self.case.pk]))
        content = response.content.decode()
        self.assertIn('fact-card', content)
        self.assertIn('analysis-card', content)

    def test_historico_do_fato_mostra_versoes_em_ordem(self):
        fact = services.record_fact(
            self.entity, self.user, campo='faturamento', valor='100', status='confirmado', fonte_descricao='f',
        )
        services.correct_fact(fact, self.user, motivo='ajuste', valor='110')
        response = self.client.get(reverse('precedentes:fact_history', args=[fact.pk]))
        content = response.content.decode()
        self.assertIn('100', content)
        self.assertIn('110', content)
        self.assertIn('ajuste', content)
