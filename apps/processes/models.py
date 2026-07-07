"""
Models do app processes.
Representa o domínio principal: o processo público monitorado.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class ProcessStatus(models.TextChoices):
    ACTIVE = 'active', _('Ativo')
    PAUSED = 'paused', _('Pausado')
    ERROR = 'error', _('Com erro')
    ARCHIVED = 'archived', _('Arquivado')


class MonitoredProcess(models.Model):
    """
    Representa uma página pública monitorada — geralmente um processo do CADE/SEI.

    O campo `source` aceita dois formatos:
      - URL pública direta (http/https)
      - Número do processo/protocolo (ex: 08700.005905/2026-38)

    Quando `source` é um número, o sistema tenta resolver a URL real e
    armazenar em `resolved_url`. O campo `effective_url` (property) sempre
    retorna a melhor opção disponível.
    """

    label = models.CharField(_('rótulo'), max_length=300)
    source = models.CharField(
        _('fonte'),
        max_length=1000,
        unique=True,
        help_text=_('URL pública ou número do processo (ex: 08700.005905/2026-38)'),
    )
    resolved_url = models.URLField(
        _('URL resolvida'),
        max_length=1000,
        blank=True,
        help_text=_('Preenchida automaticamente ao resolver número de processo.'),
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=ProcessStatus.choices,
        default=ProcessStatus.ACTIVE,
        db_index=True,
    )
    check_interval_seconds = models.PositiveIntegerField(
        _('intervalo de checagem (s)'),
        default=1500,
        help_text=_('Mínimo recomendado: 1500 s (25 min). Respeite a página pública.'),
    )
    last_hash = models.CharField(_('último hash SHA-256'), max_length=64, blank=True)
    last_text = models.TextField(_('último texto extraído'), blank=True)
    last_checked_at = models.DateTimeField(_('última checagem'), null=True, blank=True, db_index=True)
    last_changed_at = models.DateTimeField(_('última mudança'), null=True, blank=True)
    last_error = models.TextField(_('último erro'), blank=True)
    notes = models.TextField(_('observações internas'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('processo monitorado')
        verbose_name_plural = _('processos monitorados')
        ordering = ['-last_changed_at', '-updated_at']
        indexes = [
            models.Index(fields=['status', 'last_checked_at']),
        ]

    def __str__(self) -> str:
        return self.label or self.source

    @property
    def effective_url(self) -> str:
        """Retorna a URL real a ser acessada (resolved_url ou source)."""
        return self.resolved_url or self.source

    @property
    def is_active(self) -> bool:
        return self.status == ProcessStatus.ACTIVE

    @property
    def has_baseline(self) -> bool:
        return bool(self.last_hash)


class ProcessTag(models.Model):
    """Tag livre para classificar processos (ex: 'fusão', 'investigação', 'cliente-X')."""

    process = models.ForeignKey(
        MonitoredProcess,
        on_delete=models.CASCADE,
        related_name='tags',
        verbose_name=_('processo'),
    )
    name = models.CharField(_('tag'), max_length=100)

    class Meta:
        verbose_name = _('tag')
        verbose_name_plural = _('tags')
        unique_together = ('process', 'name')

    def __str__(self) -> str:
        return self.name
