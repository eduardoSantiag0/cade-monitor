"""
Models do app precedentes (spec 013): fundação da iniciativa "Precedentes" — dossiê
de due diligence com o princípio central "fato ≠ análise, tudo com evidência
anexada". Ver specs/013-precedentes-due-diligence/data-model.md para o racional.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class PrecedentCase(models.Model):
    """Um dossiê de due diligence de uma operação em análise no CADE."""

    titulo = models.CharField(_('título'), max_length=300)
    cliente = models.CharField(_('cliente'), max_length=200, blank=True)
    notas = models.TextField(_('notas'), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='precedent_cases',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('caso de due diligence')
        verbose_name_plural = _('casos de due diligence')
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.titulo


class PrecedentEntity(models.Model):
    """Uma empresa (parte) envolvida num caso de due diligence."""

    class Papel(models.TextChoices):
        REQUERENTE = 'requerente', _('Requerente')
        PARTE_IDENTIFICADA = 'parte_identificada', _('Parte identificada')
        OUTRO = 'outro', _('Outro')

    case = models.ForeignKey(PrecedentCase, on_delete=models.CASCADE, related_name='entities')
    papel = models.CharField(_('papel'), max_length=30, choices=Papel.choices, default=Papel.OUTRO)
    razao_social = models.CharField(_('razão social'), max_length=300)
    cnpj = models.CharField(_('CNPJ'), max_length=32, blank=True)
    pais = models.CharField(_('país'), max_length=100, default='Brasil')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('empresa (parte)')
        verbose_name_plural = _('empresas (partes)')
        ordering = ['razao_social']

    def __str__(self) -> str:
        return self.razao_social


class PrecedentFact(models.Model):
    """Um fato sobre uma empresa do caso — tabela append-only: cada linha é uma
    versão. `root=None` na 1ª versão (é a própria raiz do grupo); corrigir cria uma
    nova linha com `root` apontando pra raiz, nunca sobrescreve o valor existente
    (FR-006). `PrecedentAnalysis.facts` sempre referencia a linha-raiz (`root=None`),
    nunca uma versão específica — ver data-model.md."""

    class Status(models.TextChoices):
        CONFIRMADO = 'confirmado', _('Confirmado')
        CONFIRMAR_CLIENTE = 'confirmar_cliente', _('A confirmar com o cliente')
        SOLICITAR_CLIENTE = 'solicitar_cliente', _('A solicitar ao cliente')
        NAO_LOCALIZADO = 'nao_localizado', _('Não localizado')

    entity = models.ForeignKey(PrecedentEntity, on_delete=models.CASCADE, related_name='facts')
    root = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='versions',
    )
    is_current = models.BooleanField(default=True)
    campo = models.CharField(_('campo'), max_length=200)
    valor = models.TextField(_('valor'))
    status = models.CharField(_('status'), max_length=20, choices=Status.choices)
    fonte_descricao = models.CharField(_('fonte'), max_length=300, blank=True)
    fonte_url = models.URLField(_('URL da fonte'), blank=True)
    citacao = models.TextField(_('citação/trecho de evidência'), blank=True)
    motivo = models.TextField(_('motivo da correção'), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='precedent_facts',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('fato')
        verbose_name_plural = _('fatos')
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'{self.campo}: {self.valor}'

    @property
    def root_id_or_self(self) -> int:
        """A identidade estável do grupo de versões — a raiz nunca muda mesmo
        quando o fato ganha novas versões (usado por PrecedentAnalysis)."""
        return self.root_id or self.pk

    @classmethod
    def group_queryset(cls, root: 'PrecedentFact'):
        raiz = root.root_id or root.pk
        return cls.objects.filter(Q(pk=raiz) | Q(root_id=raiz))


class PrecedentAnalysis(models.Model):
    """Uma nota interpretativa do advogado, associada a fatos-base — mantida
    estruturalmente separada dos fatos (nunca misturada na mesma listagem/contagem,
    FR-010/FR-011)."""

    case = models.ForeignKey(PrecedentCase, on_delete=models.CASCADE, related_name='analyses')
    texto = models.TextField(_('análise'))
    facts = models.ManyToManyField(PrecedentFact, related_name='analyses', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='precedent_analyses',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('análise')
        verbose_name_plural = _('análises')
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.texto[:60]
