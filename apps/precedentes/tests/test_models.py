from django.contrib.auth.models import User
from django.db.models import Q
from django.test import TestCase

from apps.precedentes.models import PrecedentCase, PrecedentEntity, PrecedentFact


class PrecedentFactVersioningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('advogado')
        self.case = PrecedentCase.objects.create(created_by=self.user, titulo='Caso teste')
        self.entity = PrecedentEntity.objects.create(
            case=self.case, papel=PrecedentEntity.Papel.REQUERENTE, razao_social='Empresa X',
        )

    def test_primeira_versao_e_a_propria_raiz(self):
        fact = PrecedentFact.objects.create(
            entity=self.entity, created_by=self.user, campo='faturamento', valor='100',
            status=PrecedentFact.Status.CONFIRMADO, fonte_descricao='balanço',
        )
        self.assertIsNone(fact.root_id)
        self.assertTrue(fact.is_current)

    def test_grupo_de_versoes_encontravel_por_raiz_ou_root_id(self):
        raiz = PrecedentFact.objects.create(
            entity=self.entity, created_by=self.user, campo='faturamento', valor='100',
            status=PrecedentFact.Status.CONFIRMADO, fonte_descricao='balanço', is_current=False,
        )
        correcao1 = PrecedentFact.objects.create(
            entity=self.entity, created_by=self.user, root=raiz, campo='faturamento', valor='110',
            status=PrecedentFact.Status.CONFIRMADO, fonte_descricao='balanço', motivo='ajuste',
            is_current=False,
        )
        correcao2 = PrecedentFact.objects.create(
            entity=self.entity, created_by=self.user, root=raiz, campo='faturamento', valor='120',
            status=PrecedentFact.Status.CONFIRMADO, fonte_descricao='balanço', motivo='ajuste 2',
            is_current=True,
        )
        grupo = PrecedentFact.objects.filter(Q(pk=raiz.pk) | Q(root_id=raiz.pk))
        self.assertEqual(set(grupo), {raiz, correcao1, correcao2})
