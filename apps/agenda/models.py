"""
Models do app agenda (spec 011): calendário oficial de dias úteis do CADE, e o
estado de convites de calendário já enviados por processo. A linha do tempo de
prazos em si NUNCA é persistida — ver data-model.md.
"""
from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class CadeCalendarYear(models.Model):
    """Um registro por ano-calendário, com o status da sincronização (FR-001/002/003)."""

    class Status(models.TextChoices):
        PENDING = 'pending', _('Não confirmado')
        CONFIRMED = 'confirmed', _('Confirmado')
        CONFLICT = 'conflict', _('Com conflito')

    year = models.PositiveIntegerField(_('ano'), unique=True)
    status = models.CharField(_('status'), max_length=20, choices=Status.choices, default=Status.PENDING)
    official_act = models.CharField(_('ato oficial'), max_length=200, blank=True)
    official_source_url = models.URLField(_('URL da fonte'), max_length=1000, blank=True)
    last_checked_at = models.DateTimeField(_('última checagem'), null=True, blank=True)
    next_check_at = models.DateTimeField(_('próxima checagem permitida'), null=True, blank=True)

    class Meta:
        verbose_name = _('calendário oficial (ano)')
        verbose_name_plural = _('calendários oficiais (anos)')
        ordering = ['-year']

    def __str__(self) -> str:
        return f'{self.year} ({self.get_status_display()})'


class CadeCalendarEntry(models.Model):
    """Um dia não útil (feriado/ponto facultativo) de um ano do calendário oficial."""

    calendar_year = models.ForeignKey(
        CadeCalendarYear, on_delete=models.CASCADE, related_name='entries',
        verbose_name=_('ano do calendário'),
    )
    date = models.DateField(_('data'))
    name = models.CharField(_('nome'), max_length=200)

    class Meta:
        verbose_name = _('dia não útil (CADE)')
        verbose_name_plural = _('dias não úteis (CADE)')
        unique_together = ('calendar_year', 'date')
        ordering = ['date']

    def __str__(self) -> str:
        return f'{self.date} — {self.name}'


class ProcessInvite(models.Model):
    """O que já foi enviado como convite de calendário para um (processo, tipo de
    prazo) — decide reenviar/atualizar/cancelar (FR-012 a FR-016)."""

    class DeadlineType(models.TextChoices):
        SG_ANALYSIS = 'sg_analysis', _('Análise da SG')
        FINAL_CERTIFICATE = 'final_certificate', _('Certidão final')

    class Status(models.TextChoices):
        SENT = 'sent', _('Enviado')
        CANCELLED = 'cancelled', _('Cancelado')

    process = models.ForeignKey(
        'processes.MonitoredProcess', on_delete=models.CASCADE, related_name='agenda_invites',
        verbose_name=_('processo'),
    )
    deadline_type = models.CharField(_('tipo de prazo'), max_length=20, choices=DeadlineType.choices)
    uid = models.CharField(_('identificador do compromisso'), max_length=200)
    event_date = models.DateField(_('data enviada'))
    sequence = models.PositiveIntegerField(_('sequência'), default=0)
    status = models.CharField(_('status'), max_length=10, choices=Status.choices, default=Status.SENT)
    is_estimate = models.BooleanField(_('é estimativa'), default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('convite de calendário (processo)')
        verbose_name_plural = _('convites de calendário (processos)')
        unique_together = ('process', 'deadline_type')

    def __str__(self) -> str:
        return f'{self.get_deadline_type_display()} — {self.process} — {self.event_date}'
