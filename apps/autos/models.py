"""
Models do app autos (spec 012): fila e resultado da montagem de um pacote ZIP
com os documentos públicos de um processo. Ver
specs/012-autos-processo-pacote/data-model.md para o racional.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AutosPackageJob(models.Model):
    """Um pedido de montagem de pacote — fila (consumida pelo run_worker) e
    registro do resultado (para a view de status/download)."""

    class Status(models.TextChoices):
        QUEUED = 'queued', _('Na fila')
        PROCESSING = 'processing', _('Processando')
        READY = 'ready', _('Pronto')
        FAILED = 'failed', _('Falhou')
        EXPIRED = 'expired', _('Expirado')

    process = models.ForeignKey(
        'processes.MonitoredProcess',
        on_delete=models.CASCADE,
        related_name='autos_jobs',
        verbose_name=_('processo'),
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='autos_jobs',
        verbose_name=_('pedido por'),
    )
    status = models.CharField(_('status'), max_length=12, choices=Status.choices, default=Status.QUEUED)
    total_declared = models.PositiveIntegerField(_('total declarado'), null=True, blank=True)
    total_processed = models.PositiveIntegerField(_('total processado'), default=0)
    plan = models.JSONField(
        _('plano'), default=list, blank=True,
        help_text=_('Lista de documentos a processar, montada uma vez no início (resumível entre ciclos do worker).'),
    )
    next_index = models.PositiveIntegerField(_('próximo item do plano'), default=0)
    divergences = models.JSONField(_('divergências'), default=list, blank=True)
    file_path = models.CharField(_('arquivo'), max_length=500, blank=True)
    error = models.TextField(_('erro'), blank=True)
    expires_at = models.DateTimeField(_('expira em'), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('pacote de autos')
        verbose_name_plural = _('pacotes de autos')
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'Autos #{self.pk} — {self.process} ({self.get_status_display()})'
