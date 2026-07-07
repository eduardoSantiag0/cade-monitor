"""
Models do app subscribers.
Representa assinantes e suas assinaturas por processo.
"""
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Subscriber(models.Model):
    """
    Pessoa ou equipe que recebe notificações quando um processo muda.

    Canais disponíveis: e-mail e WhatsApp via Evolution API.
    `silent_mode` e `paused_until` permitem controle granular de recebimento.
    """

    name = models.CharField(_('nome'), max_length=200)
    email = models.EmailField(_('e-mail'), blank=True)
    phone = models.CharField(
        _('telefone (WhatsApp)'),
        max_length=30,
        blank=True,
        help_text=_('Formato: DDI+DDD+número sem espaços (ex: 5511999998888)'),
    )
    email_enabled = models.BooleanField(_('receber por e-mail'), default=True)
    whatsapp_enabled = models.BooleanField(_('receber por WhatsApp'), default=False)
    silent_mode = models.BooleanField(
        _('modo silencioso'),
        default=False,
        help_text=_('Quando ativo, nenhuma notificação é enviada independente das preferências.'),
    )
    paused_until = models.DateTimeField(
        _('notificações pausadas até'),
        null=True,
        blank=True,
        help_text=_('Se preenchido, notificações ficam suspensas até esta data.'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('assinante')
        verbose_name_plural = _('assinantes')
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    def is_reachable(self) -> bool:
        """Retorna True se o assinante deve receber notificações agora."""
        if self.silent_mode:
            return False
        if self.paused_until and timezone.now() < self.paused_until:
            return False
        return True


class ProcessSubscription(models.Model):
    """
    Vincula um assinante a um processo, com preferências por canal.
    Permite que o mesmo assinante receba por e-mail para um processo
    e só por WhatsApp para outro.
    """

    subscriber = models.ForeignKey(
        Subscriber,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name=_('assinante'),
    )
    process = models.ForeignKey(
        'processes.MonitoredProcess',
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name=_('processo'),
    )
    email_enabled = models.BooleanField(_('notificar por e-mail'), default=True)
    whatsapp_enabled = models.BooleanField(_('notificar por WhatsApp'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('assinatura')
        verbose_name_plural = _('assinaturas')
        unique_together = ('subscriber', 'process')

    def __str__(self) -> str:
        return f'{self.subscriber} → {self.process}'
