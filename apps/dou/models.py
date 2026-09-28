"""
Models do app dou (spec 009): digest diário do DOU, antecipação da véspera e confirmação
da manhã. Ver specs/009-digest-diario-dou/data-model.md para o racional de cada modelo.
"""
from __future__ import annotations

from datetime import time

from django.db import models
from django.utils.translation import gettext_lazy as _


class DouSubscription(models.Model):
    """Inscrição de um assinante existente no digest do DOU — independente de qualquer
    inscrição em processo monitorado específico."""

    subscriber = models.OneToOneField(
        'subscribers.Subscriber',
        on_delete=models.CASCADE,
        related_name='dou_subscription',
        verbose_name=_('assinante'),
    )
    enabled = models.BooleanField(_('receber o digest diário'), default=True)
    nextday_enabled = models.BooleanField(
        _('receber antecipação da véspera'),
        default=False,
        help_text=_('Antecipa, a partir do boletim do SEI, o que deve sair no DOU do dia seguinte.'),
    )
    nextday_time = models.TimeField(
        _('horário da antecipação'),
        default=time(19, 30),
        help_text=_('Horário local de envio da antecipação da véspera.'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('inscrição no digest DOU')
        verbose_name_plural = _('inscrições no digest DOU')
        ordering = ['subscriber__name']

    def __str__(self) -> str:
        return f'Digest DOU — {self.subscriber}'


class DouMonitoredTerm(models.Model):
    """Termo (pessoa, empresa ou palavra-chave) usado só para destaque visual do e-mail —
    lista própria por assinante, sem sincronia com outra lista do sistema."""

    subscription = models.ForeignKey(
        DouSubscription,
        on_delete=models.CASCADE,
        related_name='monitored_terms',
        verbose_name=_('inscrição'),
    )
    term = models.CharField(_('termo monitorado'), max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('termo monitorado (DOU)')
        verbose_name_plural = _('termos monitorados (DOU)')
        ordering = ['term']

    def __str__(self) -> str:
        return self.term


class DouSendLog(models.Model):
    """Um registro por e-mail efetivamente enviado (ou tentado) por esta feature —
    garante dedup (nunca mais de um envio do mesmo tipo/dia) e auditoria."""

    class Kind(models.TextChoices):
        DIGEST = 'digest', _('Digest diário')
        PUBDOU_ANT = 'pubdou_ant', _('Antecipação da véspera')
        PUBDOU_COMPL = 'pubdou_compl', _('Complemento da antecipação')
        PUBDOU_CONF = 'pubdou_conf', _('Confirmação da manhã')

    class Status(models.TextChoices):
        SENT = 'sent', _('Enviado')
        FAILED = 'failed', _('Falhou')

    subscription = models.ForeignKey(
        DouSubscription,
        on_delete=models.CASCADE,
        related_name='send_logs',
        verbose_name=_('inscrição'),
    )
    kind = models.CharField(_('tipo de envio'), max_length=20, choices=Kind.choices)
    reference_date = models.DateField(_('data de referência'))
    status = models.CharField(_('resultado'), max_length=10, choices=Status.choices)
    error = models.TextField(_('erro'), blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('envio do DOU')
        verbose_name_plural = _('envios do DOU')
        unique_together = ('subscription', 'kind', 'reference_date')
        ordering = ['-sent_at']

    def __str__(self) -> str:
        return f'{self.get_kind_display()} — {self.subscription} — {self.reference_date}'


class DouFetchState(models.Model):
    """Marcador de última tentativa de busca por fonte externa — implementa a cadência
    mínima entre tentativas exigida pela emenda v2.2.0 do Princípio II."""

    class Source(models.TextChoices):
        RESENHA = 'resenha', _('Resenha do CADE (sinc.cade.gov.br)')
        INGOV_LISTING = 'ingov_listing', _('Listagem in.gov.br')
        SEI_PUBLICATIONS = 'sei_publications', _('Publicações do SEI (boletim)')

    source = models.CharField(_('fonte'), max_length=20, choices=Source.choices, unique=True)
    last_attempt_at = models.DateTimeField(_('última tentativa'), null=True, blank=True)
    last_success_at = models.DateTimeField(_('último sucesso'), null=True, blank=True)

    class Meta:
        verbose_name = _('estado de busca (DOU)')
        verbose_name_plural = _('estados de busca (DOU)')

    def __str__(self) -> str:
        return self.get_source_display()


class DouAnticipation(models.Model):
    """Snapshot do que foi antecipado na véspera para um assinante, usado na manhã
    seguinte para montar a confirmação ('exceto ...')."""

    subscription = models.ForeignKey(
        DouSubscription,
        on_delete=models.CASCADE,
        related_name='anticipations',
        verbose_name=_('inscrição'),
    )
    reference_date = models.DateField(
        _('data do DOU esperado'),
        help_text=_('Data do DOU em que os itens antecipados devem sair.'),
    )
    items = models.JSONField(_('itens antecipados'), default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('antecipação DOU')
        verbose_name_plural = _('antecipações DOU')
        unique_together = ('subscription', 'reference_date')
        ordering = ['-reference_date']

    def __str__(self) -> str:
        return f'Antecipação {self.reference_date} — {self.subscription}'
