"""
Parsing das atualizações do Telegram e dos argumentos dos comandos.
Funções puras — sem banco e sem HTTP.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from apps.monitoring.extractors import PROCESS_NUMBER_RE

SEI_HOST_SUFFIX = 'cade.gov.br'
_DIGITS_ONLY_RE = re.compile(r'^\d{17}$')


class _Model(BaseModel):
    model_config = ConfigDict(extra='ignore')


class TgUser(_Model):
    id: int
    is_bot: bool = False
    first_name: str = ''
    last_name: str = ''
    username: str = ''


class TgChat(_Model):
    id: int
    type: str
    title: str = ''
    username: str = ''
    first_name: str = ''
    last_name: str = ''

    @property
    def display_name(self) -> str:
        if self.title:
            return self.title
        return ' '.join(p for p in (self.first_name, self.last_name) if p) or self.username


class TgMessage(_Model):
    message_id: int
    chat: TgChat
    from_user: TgUser | None = Field(default=None, alias='from')
    text: str = ''
    migrate_to_chat_id: int | None = None


class TgChatMember(_Model):
    status: str
    user: TgUser


class TgChatMemberUpdated(_Model):
    chat: TgChat
    from_user: TgUser | None = Field(default=None, alias='from')
    new_chat_member: TgChatMember


class TgUpdate(_Model):
    update_id: int
    message: TgMessage | None = None
    my_chat_member: TgChatMemberUpdated | None = None


@dataclass(frozen=True)
class Command:
    name: str
    args: str


def parse_command(text: str, bot_username: str = '') -> Command | None:
    """
    '/watch@MeuBot 08700...' → Command('watch', '08700...').
    Retorna None para texto que não é comando ou comando dirigido a outro bot.
    """
    text = (text or '').strip()
    if not text.startswith('/'):
        return None
    head, _, args = text.partition(' ')
    name, _, target = head[1:].partition('@')
    if target and bot_username and target.lower() != bot_username.lower():
        return None
    if not name:
        return None
    return Command(name=name.lower(), args=args.strip())


def normalize_process_ref(value: str) -> str | None:
    """
    Normaliza a referência de processo para o valor salvo em MonitoredProcess.source:
      - '08700.005905/2026-38' (com espaços ou sem pontuação) → forma canônica
      - link público do SEI do CADE → a própria URL
    Retorna None se não reconhecer o formato.
    """
    value = (value or '').strip()
    if not value:
        return None

    parsed = urlparse(value)
    if parsed.scheme in ('http', 'https') and parsed.hostname:
        host = parsed.hostname.lower()
        if host == SEI_HOST_SUFFIX or host.endswith('.' + SEI_HOST_SUFFIX):
            return value
        return None

    compact = re.sub(r'\s+', '', value)
    if PROCESS_NUMBER_RE.fullmatch(compact):
        return compact
    if _DIGITS_ONLY_RE.match(compact):
        d = compact
        return f'{d[:5]}.{d[5:11]}/{d[11:15]}-{d[15:]}'
    return None
