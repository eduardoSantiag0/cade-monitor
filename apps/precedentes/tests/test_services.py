from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.precedentes import selectors, services
from apps.precedentes.models import PrecedentAnalysis, PrecedentCase, PrecedentEntity, PrecedentFact


class CaseAndEntityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('advogado')

    def test_create_case(self):
        case = services.create_case(self.user, 'Aquisição X', cliente='Cliente Y')
        self.assertEqual(case.created_by, self.user)
        self.assertEqual(case.titulo, 'Aquisição X')

    def test_add_entity(self):
        case = services.create_case(self.user, 'Caso')
        entity = services.add_entity(case, 'requerente', 'Empresa X', cnpj='00.000.000/0001-00')
        self.assertEqual(entity.case, case)
        self.assertEqual(entity.papel, 'requerente')

    def test_update_entity_nao_cria_segunda_linha(self):
        case = services.create_case(self.user, 'Caso')
        entity = services.add_entity(case, 'outro', 'Nome Antigo')
        services.update_entity(entity, razao_social='Nome Novo', papel='requerente')
        entity.refresh_from_db()
        self.assertEqual(entity.razao_social, 'Nome Novo')
        self.assertEqual(entity.papel, 'requerente')
        self.assertEqual(PrecedentEntity.objects.filter(case=case).count(), 1)


class RecordFactTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('advogado')
        case = services.create_case(self.user, 'Caso')
        self.entity = services.add_entity(case, 'requerente', 'Empresa X')

    def test_confirmado_com_fonte_e_aceito(self):
        fact = services.record_fact(
            self.entity, self.user, campo='faturamento', valor='R$ 100', status='confirmado',
            fonte_descricao='Demonstração financeira 2025',
        )
        self.assertEqual(fact.status, 'confirmado')
        self.assertTrue(fact.is_current)

    def test_confirmado_sem_fonte_e_rejeitado(self):
        # FR-004: "confirmado sem fonte não é confirmado".
        with self.assertRaises(ValidationError):
            services.record_fact(
                self.entity, self.user, campo='faturamento', valor='R$ 100', status='confirmado',
            )
        self.assertEqual(PrecedentFact.objects.count(), 0)

    def test_valor_vazio_e_rejeitado(self):
        # FR-005.
        with self.assertRaises(ValidationError):
            services.record_fact(self.entity, self.user, campo='faturamento', valor='', status='nao_localizado')
        self.assertEqual(PrecedentFact.objects.count(), 0)

    def test_solicitar_cliente_sem_fonte_e_aceito(self):
        # FR-004 só se aplica a status='confirmado'.
        fact = services.record_fact(
            self.entity, self.user, campo='controladora', valor='desconhecida', status='solicitar_cliente',
        )
        self.assertEqual(fact.status, 'solicitar_cliente')


class CorrectFactTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('advogado')
        case = services.create_case(self.user, 'Caso')
        self.entity = services.add_entity(case, 'requerente', 'Empresa X')
        self.fact = services.record_fact(
            self.entity, self.user, campo='faturamento', valor='100', status='confirmado',
            fonte_descricao='balanço',
        )

    def test_correcao_cria_nova_versao_sem_alterar_a_anterior(self):
        nova = services.correct_fact(self.fact, self.user, motivo='valor revisado', valor='110')
        self.fact.refresh_from_db()
        self.assertFalse(self.fact.is_current)
        self.assertEqual(self.fact.valor, '100')  # FR-006: nunca sobrescreve.
        self.assertTrue(nova.is_current)
        self.assertEqual(nova.valor, '110')
        self.assertEqual(nova.root_id, self.fact.pk)

    def test_correcao_sem_motivo_e_rejeitada(self):
        # FR-007.
        with self.assertRaises(ValidationError):
            services.correct_fact(self.fact, self.user, motivo='', valor='110')
        self.fact.refresh_from_db()
        self.assertTrue(self.fact.is_current)
        self.assertEqual(self.fact.valor, '100')

    def test_duas_correcoes_produzem_tres_versoes_em_ordem(self):
        v2 = services.correct_fact(self.fact, self.user, motivo='ajuste 1', valor='110')
        v3 = services.correct_fact(v2, self.user, motivo='ajuste 2', valor='120')
        history = list(selectors.fact_history(v3))
        self.assertEqual([h.valor for h in history], ['100', '110', '120'])
        self.assertEqual([h.motivo for h in history], ['', 'ajuste 1', 'ajuste 2'])
        self.assertEqual([h.is_current for h in history], [False, False, True])

    def test_corrigir_uma_correcao_resolve_para_o_mesmo_grupo(self):
        v2 = services.correct_fact(self.fact, self.user, motivo='ajuste 1', valor='110')
        v3 = services.correct_fact(v2, self.user, motivo='ajuste 2', valor='120')
        self.assertEqual(v3.root_id, self.fact.pk)
        self.assertEqual(PrecedentFact.objects.filter(entity=self.entity).count(), 3)


class RecordAnalysisTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('advogado')
        case = services.create_case(self.user, 'Caso')
        self.entity = services.add_entity(case, 'requerente', 'Empresa X')
        self.case = case
        self.fact1 = services.record_fact(
            self.entity, self.user, campo='faturamento', valor='100', status='confirmado', fonte_descricao='f',
        )
        self.fact2 = services.record_fact(
            self.entity, self.user, campo='mercado', valor='varejo', status='confirmado', fonte_descricao='f',
        )

    def test_record_analysis_associa_fatos_base(self):
        analysis = services.record_analysis(self.case, self.user, 'Overlap potencial', [self.fact1, self.fact2])
        self.assertEqual(set(analysis.facts.all()), {self.fact1, self.fact2})

    def test_analise_sobrevive_a_correcao_do_fato_base(self):
        # FR-010: a referência permanece íntegra e resolve para o valor atual.
        analysis = services.record_analysis(self.case, self.user, 'Overlap potencial', [self.fact1])
        services.correct_fact(self.fact1, self.user, motivo='ajuste', valor='150')
        analysis.refresh_from_db()
        base = analysis.facts.get(pk=self.fact1.pk)  # a raiz continua associada.
        current = PrecedentFact.objects.get(entity=self.entity, campo='faturamento', is_current=True)
        self.assertEqual(base.pk, self.fact1.pk)
        self.assertEqual(current.valor, '150')

    def test_passar_versao_nao_raiz_resolve_para_a_raiz(self):
        corrigido = services.correct_fact(self.fact1, self.user, motivo='ajuste', valor='150')
        analysis = services.record_analysis(self.case, self.user, 'Overlap', [corrigido])
        self.assertEqual(list(analysis.facts.values_list('pk', flat=True)), [self.fact1.pk])


class RemoveEntityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('advogado')
        self.case = services.create_case(self.user, 'Caso')

    def test_remove_entity_apaga_fatos_e_analises_orfas(self):
        entity = services.add_entity(self.case, 'requerente', 'Empresa X')
        fact = services.record_fact(
            entity, self.user, campo='faturamento', valor='100', status='confirmado', fonte_descricao='f',
        )
        analysis = services.record_analysis(self.case, self.user, 'Nota', [fact])

        services.remove_entity(entity)

        self.assertFalse(PrecedentEntity.objects.filter(pk=entity.pk).exists())
        self.assertFalse(PrecedentFact.objects.filter(pk=fact.pk).exists())
        self.assertFalse(PrecedentAnalysis.objects.filter(pk=analysis.pk).exists())

    def test_analise_com_fatos_de_outra_empresa_sobrevive(self):
        entity1 = services.add_entity(self.case, 'requerente', 'Empresa X')
        entity2 = services.add_entity(self.case, 'parte_identificada', 'Empresa Y')
        fact1 = services.record_fact(
            entity1, self.user, campo='faturamento', valor='100', status='confirmado', fonte_descricao='f',
        )
        fact2 = services.record_fact(
            entity2, self.user, campo='mercado', valor='varejo', status='confirmado', fonte_descricao='f',
        )
        analysis = services.record_analysis(self.case, self.user, 'Overlap', [fact1, fact2])

        services.remove_entity(entity1)

        analysis.refresh_from_db()
        self.assertTrue(PrecedentAnalysis.objects.filter(pk=analysis.pk).exists())
        self.assertEqual(list(analysis.facts.values_list('pk', flat=True)), [fact2.pk])
