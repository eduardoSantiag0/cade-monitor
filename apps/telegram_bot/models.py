"""
Models do app telegram_bot.
Cada conversa (privada ou grupo) é um Subscriber, para reaproveitar o fluxo
de notificações. Ações que dependem do SEI viram BotAction e são executadas
pelo run_worker — o webhook nunca faz scraping (constituição, Princípio I).
"""
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ChatType(models.TextChoices):
    PRIVATE = 'private', _('Privado')
    GROUP = 'group', _('Grupo')
    SUPERGROUP = 'supergroup', _('Supergrupo')


class TelegramChat(models.Model):
    """Conversa em que o bot atua. `chat_id` muda quando um grupo vira supergrupo."""

    chat_id = models.BigIntegerField(_('ID do chat'), unique=True)
    chat_type = models.CharField(_('tipo'), max_length=20, choices=ChatType.choices)
    title = models.CharField(_('nome/título'), max_length=255, blank=True)
    username = models.CharField(_('usuário'), max_length=64, blank=True)
    is_reachable = models.BooleanField(
        _('alcançável'),
        default=True,
        help_text=_('Falso quando o usuário bloqueou o bot ou o bot saiu do grupo.'),
    )
    subscriber = models.OneToOneField(
        'subscribers.Subscriber',
        on_delete=models.CASCADE,
        related_name='telegram_chat',
        verbose_name=_('assinante'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen_at = models.DateTimeField(_('última interação'), null=True, blank=True)

    class Meta:
        verbose_name = _('chat do Telegram')
        verbose_name_plural = _('chats do Telegram')
        ordering = ['-last_seen_at']

    def __str__(self) -> str:
        return f'{self.title or self.chat_id} ({self.get_chat_type_display()})'

    @property
    def is_group(self) -> bool:
        return self.chat_type in (ChatType.GROUP, ChatType.SUPERGROUP)


class TelegramUpdate(models.Model):
    """update_id já processado — garante idempotência do webhook."""

    update_id = models.BigIntegerField(_('update_id'), unique=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('atualização recebida')
        verbose_name_plural = _('atualizações recebidas')

    def __str__(self) -> str:
        return str(self.update_id)


class BotActionKind(models.TextChoices):
    INITIAL_WATCH = 'initial_watch', _('Primeira leitura (/watch)')
    CHECK = 'check', _('Verificação sob demanda (/check)')
    LATEST = 'latest', _('Última atualização com documento (/last_update)')


class BotActionStatus(models.TextChoices):
    PENDING = 'pending', _('Pendente')
    DONE = 'done', _('Concluída')
    FAILED = 'failed', _('Falhou')
    CANCELLED = 'cancelled', _('Cancelada')


class BotAction(models.Model):
    """Pedido do bot que exige consulta ao SEI; executado pelo run_worker."""

    kind = models.CharField(_('tipo'), max_length=20, choices=BotActionKind.choices)
    chat = models.ForeignKey(
        TelegramChat, on_delete=models.CASCADE, related_name='actions', verbose_name=_('chat'),
    )
    process = models.ForeignKey(
        'processes.MonitoredProcess',
        on_delete=models.CASCADE,
        related_name='bot_actions',
        verbose_name=_('processo'),
    )
    status = models.CharField(
        _('status'), max_length=20, choices=BotActionStatus.choices, default=BotActionStatus.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(_('tentativas'), default=0)
    next_attempt_at = models.DateTimeField(_('próxima tentativa'), default=timezone.now)
    result_message = models.TextField(_('resultado'), blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(_('concluída em'), null=True, blank=True)

    class Meta:
        verbose_name = _('ação do bot')
        verbose_name_plural = _('ações do bot')
        ordering = ['requested_at']
        indexes = [models.Index(fields=['status', 'next_attempt_at'])]

    def __str__(self) -> str:
        return f'{self.get_kind_display()} — {self.process} [{self.get_status_display()}]'
