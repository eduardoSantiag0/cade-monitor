"""
Models do app notifications.
Registra cada tentativa de notificação com status e histórico de envio.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class NotificationChannel(models.TextChoices):
    EMAIL = 'email', _('E-mail')
    WHATSAPP = 'whatsapp', _('WhatsApp')


class NotificationStatus(models.TextChoices):
    PENDING = 'pending', _('Pendente')
    SENT = 'sent', _('Enviado')
    FAILED = 'failed', _('Falhou')
    SKIPPED = 'skipped', _('Ignorado')
    CHANNEL_NOT_CONFIGURED = 'channel_not_configured', _('Canal não configurado')
    INVALID_RECIPIENT = 'invalid_recipient', _('Destinatário inválido')


class Notification(models.Model):
    """
    Representa uma notificação a ser enviada (ou já enviada) para um destinatário
    em decorrência de uma mudança detectada.

    O campo `attempts` controla quantas tentativas já foram feitas,
    evitando loops infinitos de reenvio.
    """

    change = models.ForeignKey(
        'monitoring.DetectedChange',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name=_('mudança'),
    )
    subscriber = models.ForeignKey(
        'subscribers.Subscriber',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name=_('assinante'),
    )
    channel = models.CharField(_('canal'), max_length=20, choices=NotificationChannel.choices)
    destination = models.CharField(_('destino'), max_length=300)
    status = models.CharField(
        _('status'),
        max_length=30,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
        db_index=True,
    )
    error_message = models.TextField(_('mensagem de erro'), blank=True)
    attempts = models.PositiveSmallIntegerField(_('tentativas'), default=0)
    sent_at = models.DateTimeField(_('enviado em'), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('notificação')
        verbose_name_plural = _('notificações')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['change', 'channel']),
        ]

    def __str__(self) -> str:
        return f'[{self.channel}] {self.destination} → {self.get_status_display()}'


class NotificationAttempt(models.Model):
    """
    Log imutável de cada tentativa de envio de uma notificação.
    Útil para depuração e auditoria sem poluir o model Notification.
    """

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name='attempt_log',
        verbose_name=_('notificação'),
    )
    attempted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(_('status'), max_length=30)
    error = models.TextField(_('erro'), blank=True)

    class Meta:
        verbose_name = _('tentativa de envio')
        verbose_name_plural = _('tentativas de envio')
        ordering = ['-attempted_at']

    def __str__(self) -> str:
        return f'Tentativa #{self.pk} [{self.status}]'
