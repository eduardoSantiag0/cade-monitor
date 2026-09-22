"""
Models do app monitoring.
Representa a execução das checagens e os artefatos gerados: snapshots e mudanças.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class CheckStatus(models.TextChoices):
    STARTED = 'started', _('Iniciado')
    SUCCESS = 'success', _('Sucesso')
    NO_CHANGE = 'no_change', _('Sem mudança')
    CHANGED = 'changed', _('Mudança detectada')
    FAILED = 'failed', _('Falhou')


class ChangeReview(models.TextChoices):
    NONE = '', _('Não revisado')
    ANALYZED = 'analyzed', _('Analisado')
    IGNORED = 'ignored', _('Ignorado')
    IMPORTANT = 'important', _('Importante')
    FALSE_POSITIVE = 'false_positive', _('Falso positivo')


class CheckRun(models.Model):
    """
    Registro de uma execução de checagem.
    Cada vez que o worker verifica um processo, um CheckRun é criado.
    Funciona como log de auditoria do monitoramento.
    """

    process = models.ForeignKey(
        'processes.MonitoredProcess',
        on_delete=models.CASCADE,
        related_name='check_runs',
        verbose_name=_('processo'),
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=CheckStatus.choices,
        default=CheckStatus.STARTED,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(_('finalizado em'), null=True, blank=True)
    error_message = models.TextField(_('mensagem de erro'), blank=True)

    class Meta:
        verbose_name = _('execução de checagem')
        verbose_name_plural = _('execuções de checagem')
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['process', '-started_at']),
        ]

    def __str__(self) -> str:
        return f'CheckRun #{self.pk} [{self.get_status_display()}] — {self.process}'


class PageSnapshot(models.Model):
    """
    Snapshot do conteúdo textual extraído de uma página em um momento específico.
    Não armazena HTML bruto — somente o texto normalizado e o hash SHA-256.
    Isso mantém o banco compacto e os diffs eficientes.
    """

    process = models.ForeignKey(
        'processes.MonitoredProcess',
        on_delete=models.CASCADE,
        related_name='snapshots',
        verbose_name=_('processo'),
    )
    check_run = models.ForeignKey(
        CheckRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='snapshots',
        verbose_name=_('execução'),
    )
    content_hash = models.CharField(_('hash SHA-256'), max_length=64, db_index=True)
    text_content = models.TextField(_('conteúdo extraído'))
    fetched_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('snapshot de página')
        verbose_name_plural = _('snapshots de página')
        ordering = ['-fetched_at']
        indexes = [
            models.Index(fields=['process', '-fetched_at']),
        ]

    def __str__(self) -> str:
        return f'Snapshot #{self.pk} — {self.process} ({self.fetched_at:%Y-%m-%d %H:%M})'


class DetectedChange(models.Model):
    """
    Registra uma mudança real detectada entre dois snapshots consecutivos.
    Contém o resumo humanizado e o diff textual.

    O campo `review` permite que a equipe classifique a mudança manualmente,
    transformando o sistema num radar colaborativo.
    """

    process = models.ForeignKey(
        'processes.MonitoredProcess',
        on_delete=models.CASCADE,
        related_name='changes',
        verbose_name=_('processo'),
    )
    check_run = models.ForeignKey(
        CheckRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='changes',
        verbose_name=_('execução'),
    )
    old_snapshot = models.ForeignKey(
        PageSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='as_old',
        verbose_name=_('snapshot anterior'),
    )
    new_snapshot = models.ForeignKey(
        PageSnapshot,
        on_delete=models.CASCADE,
        related_name='as_new',
        verbose_name=_('snapshot novo'),
    )
    old_hash = models.CharField(_('hash anterior'), max_length=64, blank=True)
    new_hash = models.CharField(_('hash novo'), max_length=64)
    summary = models.TextField(_('resumo'))
    diff_text = models.TextField(_('diff'))
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    review = models.CharField(
        _('revisão humana'),
        max_length=20,
        choices=ChangeReview.choices,
        blank=True,
        db_index=True,
    )
    reviewer_notes = models.TextField(_('observações do revisor'), blank=True)

    class Meta:
        verbose_name = _('mudança detectada')
        verbose_name_plural = _('mudanças detectadas')
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['process', '-detected_at']),
            models.Index(fields=['review', '-detected_at']),
        ]

    def __str__(self) -> str:
        return f'Mudança #{self.pk} — {self.process} ({self.detected_at:%Y-%m-%d %H:%M})'


class DetectedDocumentMode(models.TextChoices):
    ATTACHMENT = 'attachment', _('Anexo')
    LINK_ONLY = 'link_only', _('Somente link')


class DetectedDocumentStatus(models.TextChoices):
    PENDING_RETRY = 'pending_retry', _('Pendente para retentativa')
    DELIVERED = 'delivered', _('Entregue')
    LINK_ONLY_NOTIFIED = 'link_only_notified', _('Notificado com link')
    FAILED = 'failed', _('Falhou')


class DetectedDocument(models.Model):
    """Documento novo detectado na mudança, com estado para entrega de anexo."""

    change = models.ForeignKey(
        DetectedChange,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name=_('mudança'),
    )
    document_number = models.CharField(_('número do documento'), max_length=120, blank=True)
    title = models.CharField(_('título/tipo'), max_length=240, blank=True)
    url = models.TextField(_('link público no SEI'), blank=True)
    mode = models.CharField(
        _('modo de entrega'),
        max_length=20,
        choices=DetectedDocumentMode.choices,
        default=DetectedDocumentMode.ATTACHMENT,
    )
    status = models.CharField(
        _('status de entrega'),
        max_length=30,
        choices=DetectedDocumentStatus.choices,
        default=DetectedDocumentStatus.PENDING_RETRY,
        db_index=True,
    )
    retryable = models.BooleanField(_('permite retentativa'), default=True)
    failure_reason = models.TextField(_('motivo da falha'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('documento detectado')
        verbose_name_plural = _('documentos detectados')
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['change', 'status']),
        ]

    def __str__(self) -> str:
        return f'{self.document_number or "Documento"} [{self.get_status_display()}]'


class AppSetting(models.Model):
    """
    Par chave/valor para configurações runtime do sistema.
    Evita precisar de um manage.py ou restart para ajustes simples.
    Usado internamente pelo sistema; não exposto via interface pública.
    """

    key = models.CharField(_('chave'), max_length=100, unique=True)
    value = models.TextField(_('valor'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('configuração do sistema')
        verbose_name_plural = _('configurações do sistema')

    def __str__(self) -> str:
        return f'{self.key} = {self.value[:60]}'

    @classmethod
    def get(cls, key: str, default: str = '') -> str:
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key: str, value: str) -> None:
        cls.objects.update_or_create(key=key, defaults={'value': str(value)})
