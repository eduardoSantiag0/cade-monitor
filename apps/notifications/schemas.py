"""
Schemas Pydantic para validar os payloads que cruzam a fronteira dos canais
de notificação (e-mail e WhatsApp/Evolution API).

Objetivo: validar formato/tipos antes de montar a requisição HTTP ou o
e-mail, com mensagens de erro claras — sem mudar os contratos públicos
(dict/tuple) já usados pelos serviços e testes existentes.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmailAttachment(BaseModel):
    """Anexo de e-mail: conteúdo binário + metadados mínimos."""

    model_config = ConfigDict(frozen=True)

    filename: str = Field(default='documento', max_length=140)
    content_type: str = 'application/octet-stream'
    content: bytes = Field(repr=False)

    @field_validator('filename', mode='before')
    @classmethod
    def _default_filename(cls, value: object) -> object:
        return value or 'documento'

    @field_validator('content_type', mode='after')
    @classmethod
    def _split_mime(cls, value: str) -> str:
        maintype, _, subtype = value.partition('/')
        if not subtype:
            return 'application/octet-stream'
        return value


class InvalidPhoneNumber(ValueError):
    """Número de telefone não atende ao formato aceito pela Evolution API."""


def normalize_whatsapp_phone(phone: str) -> str:
    """
    Remove formatação do número e valida que restam apenas dígitos com
    tamanho mínimo plausível (DDI + DDD + número).
    Levanta InvalidPhoneNumber se o valor não for aproveitável.
    """
    cleaned = (
        (phone or '').strip()
        .replace('+', '').replace(' ', '').replace('-', '')
        .replace('(', '').replace(')', '')
    )
    if not cleaned.isdigit() or len(cleaned) < 10:
        raise InvalidPhoneNumber(f'Número de telefone inválido: {phone!r}')
    return cleaned


class EvolutionTextPayload(BaseModel):
    """Corpo da requisição de texto para /message/sendText/{instance}."""

    model_config = ConfigDict(frozen=True)

    number: str
    text: str

    @field_validator('number', mode='after')
    @classmethod
    def _validate_number(cls, value: str) -> str:
        return normalize_whatsapp_phone(value)


class EvolutionMediaPayload(BaseModel):
    """Corpo da requisição de mídia para /message/sendMedia/{instance}."""

    model_config = ConfigDict(frozen=True)

    number: str
    mediatype: str = 'document'
    media: str
    fileName: str = Field(default='documento', max_length=140)
    caption: str = ''

    @field_validator('number', mode='after')
    @classmethod
    def _validate_number(cls, value: str) -> str:
        return normalize_whatsapp_phone(value)

    @field_validator('fileName', mode='before')
    @classmethod
    def _default_filename(cls, value: object) -> object:
        return value or 'documento'
