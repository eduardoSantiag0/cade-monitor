"""Helpers compartilhados pelos testes do bot do Telegram."""
from itertools import count

from django.test import override_settings

from apps.telegram_bot.client import TelegramResult

SECRET = 'segredo-de-teste-1234567890'
BOT = 'ExemploBot'
PROC = '08700.005905/2026-38'

telegram_settings = override_settings(
    TELEGRAM_ENABLED=True,
    TELEGRAM_BOT_TOKEN='123:ABC',
    TELEGRAM_WEBHOOK_SECRET=SECRET,
    TELEGRAM_BOT_USERNAME=BOT,
    TELEGRAM_MAX_PROCESSES_PER_CHAT=3,
    TELEGRAM_CHECK_COOLDOWN_SECONDS=300,
    TELEGRAM_HISTORY_LIMIT=2,
)

_ids = count(1000)
OK = TelegramResult(ok=True, result={'message_id': 1})


def message_update(text, chat_id=111, chat_type='private', user_id=111, title='Ana', **message_extra):
    chat = {'id': chat_id, 'type': chat_type}
    if chat_type == 'private':
        chat['first_name'] = title
    else:
        chat['title'] = title
    message = {
        'message_id': next(_ids),
        'chat': chat,
        'from': {'id': user_id, 'is_bot': False, 'first_name': 'Ana'},
        'text': text,
        **message_extra,
    }
    return {'update_id': next(_ids), 'message': message}


def member_update(status, chat_id=-500, chat_type='group'):
    return {
        'update_id': next(_ids),
        'my_chat_member': {
            'chat': {'id': chat_id, 'type': chat_type, 'title': 'Equipe'},
            'from': {'id': 1, 'is_bot': False, 'first_name': 'Adm'},
            'new_chat_member': {'status': status, 'user': {'id': 999, 'is_bot': True, 'first_name': 'Bot'}},
        },
    }


def sent_texts(mock_send):
    return [c.args[1] for c in mock_send.call_args_list]
