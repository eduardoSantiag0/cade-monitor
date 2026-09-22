"""
Serviços do bot do Telegram.

Ponto de entrada: handle_update(payload), chamado pelo webhook.
Cada comando tem um handler `cmd_<nome>(chat, args) -> str` que devolve o texto
da resposta (testável sem HTTP); handle_update é quem envia.

Regra de ouro (constituição, Princípio I): nada aqui consulta o SEI. O que
depende de scraping vira BotAction e é executado pelo run_worker (actions.py).
"""
from __future__ import annotations

import logging
import math
from collections.abc import Callable

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.processes.models import MonitoredProcess, ProcessOrigin, ProcessStatus
from apps.subscribers.models import ProcessSubscription, Subscriber

from . import client, messages, selectors
from .models import BotAction, BotActionKind, BotActionStatus, ChatType, TelegramChat
from .parsing import TgChat, TgChatMemberUpdated, TgMessage, TgUpdate, normalize_process_ref, parse_command

logger = logging.getLogger(__name__)

# Comandos que alteram o que o chat acompanha: em grupos, só administradores.
MANAGEMENT_COMMANDS = {'watch', 'unwatch', 'pause', 'resume'}
ADMIN_STATUSES = {'creator', 'administrator'}
GONE_STATUSES = {'left', 'kicked'}

_bot_username_cache: str | None = None


# ---------------------------------------------------------------------------
# Entrada do webhook
# ---------------------------------------------------------------------------


def handle_update(payload: dict) -> None:
    update = TgUpdate.model_validate(payload)

    if update.my_chat_member:
        _handle_membership(update.my_chat_member)
        return

    message = update.message
    if message is None or message.chat.type not in ChatType.values:
        return  # canais de broadcast e tipos desconhecidos são ignorados

    if message.migrate_to_chat_id:
        migrate_chat(message.chat.id, message.migrate_to_chat_id)
        return

    command = parse_command(message.text, get_bot_username())
    if command is None:
        # Em grupos, texto livre não é conosco. No privado, orienta o usuário.
        if message.chat.type == ChatType.PRIVATE and message.text:
            chat = get_or_create_chat(message.chat)
            reply(chat, messages.unknown_command())
        return

    chat = get_or_create_chat(message.chat)
    handler = COMMANDS.get(command.name)
    if handler is None:
        reply(chat, messages.unknown_command())
        return

    if command.name in MANAGEMENT_COMMANDS and chat.is_group:
        denial = _group_admin_denial(message, command.name)
        if denial:
            reply(chat, denial)
            return

    reply(chat, handler(chat, command.args))


def reply(chat: TelegramChat, text: str) -> None:
    result = client.send_message(chat.chat_id, text)
    if not result.ok and result.is_blocked:
        mark_chat_unreachable(chat.chat_id)


def get_bot_username() -> str:
    """Username do bot (sem @): env ou getMe, com cache em memória do processo."""
    global _bot_username_cache
    if settings.TELEGRAM_BOT_USERNAME:
        return settings.TELEGRAM_BOT_USERNAME
    if _bot_username_cache is None:
        result = client.get_me()
        if not result.ok:
            return ''  # sem username conhecido, aceita /cmd@qualquer (melhor que ignorar tudo)
        _bot_username_cache = str((result.result or {}).get('username') or '')
    return _bot_username_cache


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------


def get_or_create_chat(tg_chat: TgChat) -> TelegramChat:
    """Cadastro automático (acesso aberto). Qualquer mensagem torna o chat alcançável."""
    name = (tg_chat.display_name or f'Telegram {tg_chat.id}')[:255]
    now = timezone.now()
    chat = TelegramChat.objects.filter(chat_id=tg_chat.id).select_related('subscriber').first()
    if chat is None:
        with transaction.atomic():
            subscriber = Subscriber.objects.create(
                name=name[:200], email_enabled=False, whatsapp_enabled=False,
            )
            try:
                with transaction.atomic():
                    return TelegramChat.objects.create(
                        chat_id=tg_chat.id,
                        chat_type=tg_chat.type,
                        title=name,
                        username=tg_chat.username[:64],
                        subscriber=subscriber,
                        last_seen_at=now,
                    )
            except IntegrityError:
                # Outra thread criou o mesmo chat ao mesmo tempo.
                subscriber.delete()
                chat = TelegramChat.objects.get(chat_id=tg_chat.id)

    chat.title = name
    chat.username = tg_chat.username[:64]
    chat.chat_type = tg_chat.type
    chat.is_reachable = True
    chat.last_seen_at = now
    chat.save(update_fields=['title', 'username', 'chat_type', 'is_reachable', 'last_seen_at', 'updated_at'])
    return chat


def mark_chat_unreachable(chat_id: int | str) -> None:
    updated = TelegramChat.objects.filter(chat_id=int(chat_id)).update(is_reachable=False)
    if updated:
        logger.info('[telegram] Chat %s marcado como inalcançável.', chat_id)


def migrate_chat(old_chat_id: int, new_chat_id: int) -> None:
    """Grupo virou supergrupo: o chat_id muda; assinaturas seguem via FK."""
    if TelegramChat.objects.filter(chat_id=new_chat_id).exists():
        return
    updated = TelegramChat.objects.filter(chat_id=old_chat_id).update(
        chat_id=new_chat_id, chat_type=ChatType.SUPERGROUP,
    )
    if updated:
        logger.info('[telegram] Chat %s migrado para %s.', old_chat_id, new_chat_id)


def _handle_membership(event: TgChatMemberUpdated) -> None:
    """O próprio bot foi bloqueado/removido ou voltou a um chat."""
    status = event.new_chat_member.status
    if status in GONE_STATUSES:
        mark_chat_unreachable(event.chat.id)
    elif event.chat.type in ChatType.values:
        TelegramChat.objects.filter(chat_id=event.chat.id).update(is_reachable=True)


def _group_admin_denial(message: TgMessage, command: str) -> str | None:
    if message.from_user is None:
        return messages.admin_check_failed()
    result = client.get_chat_member(message.chat.id, message.from_user.id)
    if not result.ok:
        return messages.admin_check_failed()
    if (result.result or {}).get('status') not in ADMIN_STATUSES:
        return messages.admin_only(command)
    return None


# ---------------------------------------------------------------------------
# Regras de negócio compartilhadas
# ---------------------------------------------------------------------------


def recalculate_process_status(process: MonitoredProcess) -> None:
    """
    Só processos criados pelo bot têm o status gerenciado aqui (research R6):
    ACTIVE com ≥1 assinatura não pausada; PAUSED sem nenhuma.
    Processos do painel nunca são pausados/reativados pelo bot.
    """
    if process.origin != ProcessOrigin.TELEGRAM:
        return
    has_active = process.subscriptions.filter(paused=False).exists()
    new_status = process.status
    if has_active and process.status == ProcessStatus.PAUSED:
        new_status = ProcessStatus.ACTIVE
    elif not has_active and process.status in (ProcessStatus.ACTIVE, ProcessStatus.ERROR):
        new_status = ProcessStatus.PAUSED
    if new_status != process.status:
        process.status = new_status
        process.save(update_fields=['status', 'updated_at'])


def queue_action(chat: TelegramChat, process: MonitoredProcess, kind: str) -> BotAction:
    """No máximo uma ação pendente por (chat, processo, tipo)."""
    action, _ = BotAction.objects.get_or_create(
        chat=chat, process=process, kind=kind, status=BotActionStatus.PENDING,
    )
    return action


def _resolve_subscription(chat: TelegramChat, args: str, command: str):
    """Retorna (subscription, None) ou (None, texto de erro)."""
    if not args:
        return None, messages.missing_arg(command)
    ref = normalize_process_ref(args)
    if ref is None:
        return None, messages.invalid_ref()
    subscription = selectors.find_chat_subscription(chat, ref)
    if subscription is None:
        return None, messages.not_following(ref)
    return subscription, None


# ---------------------------------------------------------------------------
# Handlers de comando
# ---------------------------------------------------------------------------


def cmd_start(chat: TelegramChat, args: str) -> str:
    return messages.welcome(chat.is_group, settings.TELEGRAM_MAX_PROCESSES_PER_CHAT)


def cmd_help(chat: TelegramChat, args: str) -> str:
    return messages.help_text()


def cmd_watch(chat: TelegramChat, args: str) -> str:
    if not args:
        return messages.missing_arg('watch')
    ref = normalize_process_ref(args)
    if ref is None:
        return messages.invalid_ref()

    subscriptions = selectors.chat_subscriptions(chat)
    existing = subscriptions.filter(process__source=ref).first()
    if existing:
        return messages.already_following(existing.process.label)
    count = subscriptions.count()
    if count >= settings.TELEGRAM_MAX_PROCESSES_PER_CHAT:
        return messages.limit_reached(count)

    # Nada de _try_resolve_url aqui: resolver a URL é scraping (feito no worker).
    process, _created = MonitoredProcess.objects.get_or_create(
        source=ref,
        defaults={
            'label': ref[:300],
            'origin': ProcessOrigin.TELEGRAM,
            'status': ProcessStatus.ACTIVE,
            'check_interval_seconds': settings.CHECK_INTERVAL_SECONDS,
        },
    )
    ProcessSubscription.objects.get_or_create(
        subscriber_id=chat.subscriber_id,
        process=process,
        defaults={'email_enabled': False, 'whatsapp_enabled': False, 'telegram_enabled': True},
    )
    recalculate_process_status(process)

    if not process.has_baseline:
        # Primeira leitura no worker; ao terminar, ele também envia a última atualização.
        queue_action(chat, process, BotActionKind.INITIAL_WATCH)
        return messages.watch_queued(ref)

    # Processo já conhecido: confirma na hora e já busca a última atualização com documento.
    queue_action(chat, process, BotActionKind.LATEST)
    text = messages.watch_started(process.label)
    if process.status in (ProcessStatus.PAUSED, ProcessStatus.ARCHIVED):
        text += messages.admin_suspended_note()
    return text


def cmd_unwatch(chat: TelegramChat, args: str) -> str:
    subscription, error = _resolve_subscription(chat, args, 'unwatch')
    if error:
        return error
    process = subscription.process
    subscription.delete()
    BotAction.objects.filter(chat=chat, process=process, status=BotActionStatus.PENDING).update(
        status=BotActionStatus.CANCELLED, finished_at=timezone.now(),
    )
    recalculate_process_status(process)
    return messages.unwatched(process.label)


def cmd_list(chat: TelegramChat, args: str) -> str:
    items = [
        (sub.process.label, sub.paused, sub.process.last_checked_at)
        for sub in selectors.chat_subscriptions(chat)
    ]
    if not items:
        return messages.list_empty()
    return messages.list_items(items, settings.TELEGRAM_MAX_PROCESSES_PER_CHAT)


def cmd_status(chat: TelegramChat, args: str) -> str:
    subscription, error = _resolve_subscription(chat, args, 'status')
    if error:
        return error
    process = subscription.process
    return messages.status(
        label=process.label,
        url=process.effective_url,
        last_change=selectors.last_change(process),
        last_checked=process.last_checked_at,
        records=selectors.latest_records(process),
        paused=subscription.paused,
    )


def cmd_history(chat: TelegramChat, args: str) -> str:
    subscription, error = _resolve_subscription(chat, args, 'history')
    if error:
        return error
    process = subscription.process
    return messages.history(process.label, selectors.process_history(process, settings.TELEGRAM_HISTORY_LIMIT))


def cmd_pause(chat: TelegramChat, args: str) -> str:
    subscription, error = _resolve_subscription(chat, args, 'pause')
    if error:
        return error
    subscription.paused = True
    subscription.save(update_fields=['paused'])
    recalculate_process_status(subscription.process)
    return messages.paused(subscription.process.label)


def cmd_resume(chat: TelegramChat, args: str) -> str:
    subscription, error = _resolve_subscription(chat, args, 'resume')
    if error:
        return error
    subscription.paused = False
    subscription.save(update_fields=['paused'])
    recalculate_process_status(subscription.process)
    return messages.resumed(subscription.process.label)


def cmd_check(chat: TelegramChat, args: str) -> str:
    subscription, error = _resolve_subscription(chat, args, 'check')
    if error:
        return error
    process = subscription.process
    cooldown = settings.TELEGRAM_CHECK_COOLDOWN_SECONDS
    if process.last_checked_at:
        elapsed = (timezone.now() - process.last_checked_at).total_seconds()
        if elapsed < cooldown:
            minutes_left = max(1, math.ceil((cooldown - elapsed) / 60))
            return messages.check_cooldown(
                process.label, process.last_checked_at, minutes_left, selectors.latest_records(process),
            )
    queue_action(chat, process, BotActionKind.CHECK)
    return messages.check_queued(process.label)


def cmd_last_update(chat: TelegramChat, args: str) -> str:
    """Baixar o documento é acesso ao SEI → vira ação do worker (nunca no webhook)."""
    subscription, error = _resolve_subscription(chat, args, 'last_update')
    if error:
        return error
    process = subscription.process
    if not process.has_baseline:
        return messages.latest_no_data(process.label)
    queue_action(chat, process, BotActionKind.LATEST)
    return messages.latest_queued(process.label)


COMMANDS: dict[str, Callable[[TelegramChat, str], str]] = {
    'start': cmd_start,
    'help': cmd_help,
    'watch': cmd_watch,
    'unwatch': cmd_unwatch,
    'list': cmd_list,
    'status': cmd_status,
    'history': cmd_history,
    'pause': cmd_pause,
    'resume': cmd_resume,
    'check': cmd_check,
    'last_update': cmd_last_update,
}
