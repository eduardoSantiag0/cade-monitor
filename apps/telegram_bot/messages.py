"""
Textos do bot em português (constituição, Princípio VI).
Centralizados aqui para manter o tom consistente e facilitar revisão.
"""
from __future__ import annotations

from django.utils.timezone import localtime

EXAMPLE = '08700.005905/2026-38'

COMMANDS_HELP = (
    'Comandos:\n'
    f'/watch <processo> — começar a monitorar (ex.: /watch {EXAMPLE})\n'
    '/unwatch <processo> — parar de monitorar\n'
    '/list — processos acompanhados\n'
    '/status <processo> — última movimentação conhecida\n'
    '/check <processo> — verificar agora\n'
    '/pause <processo> — pausar alertas\n'
    '/resume <processo> — retomar alertas\n'
    '/history <processo> — últimas movimentações\n'
    '/ultima <processo> — última atualização com o PDF do documento'
)


def welcome(is_group: bool, limit: int) -> str:
    audience = (
        'Neste grupo, os alertas chegam para todos os membros, e só administradores '
        'escolhem quais processos acompanhar.'
        if is_group else
        'Você recebe um aviso aqui assim que eu detectar uma movimentação nova.'
    )
    return (
        '👋 Olá! Eu sou o CADE Monitor.\n\n'
        'Acompanho processos públicos do CADE no SEI e aviso quando aparece uma movimentação '
        f'ou documento novo. {audience}\n\n'
        f'Cada conversa pode acompanhar até {limit} processos.\n\n'
        f'{COMMANDS_HELP}'
    )


def help_text() -> str:
    return COMMANDS_HELP


def unknown_command() -> str:
    return 'Não entendi. ' + COMMANDS_HELP


def fmt_dt(value) -> str:
    return localtime(value).strftime('%d/%m/%Y às %H:%M') if value else 'nunca'


def missing_arg(command: str) -> str:
    return f'Informe o número do processo. Ex.: /{command} {EXAMPLE}'


def invalid_ref() -> str:
    return f'Número inválido. Use o formato {EXAMPLE} ou o link público do processo no SEI.'


def not_following(ref: str) -> str:
    return f'Você não acompanha o processo {ref}. Use /list para ver os seus.'


def admin_only(command: str) -> str:
    return f'Neste grupo, só administradores podem usar /{command}.'


def admin_check_failed() -> str:
    return 'Não consegui confirmar se você é administrador do grupo. Tente de novo em instantes.'


def limit_reached(count: int) -> str:
    return (
        f'Você já acompanha {count} processos, que é o limite. '
        'Use /unwatch para liberar espaço.'
    )


def already_following(label: str) -> str:
    return f'Você já acompanha {label}. Use /status para ver a situação.'


def watch_queued(ref: str) -> str:
    return f'🔎 Consultando o processo {ref} pela primeira vez. Aviso aqui em instantes.'


def latest_block(records: list[str]) -> str:
    if not records:
        return 'Ainda não identifiquei movimentações na página do processo.'
    return 'Últimas movimentações:\n' + '\n'.join(f'• {r}' for r in records)


def watch_started(label: str, url: str, records: list[str]) -> str:
    return f'✅ Pronto! Agora acompanho {label}.\n\n{latest_block(records)}\n\n🔗 {url}'


def admin_suspended_note() -> str:
    return (
        '\n\n⚠️ O monitoramento deste processo está suspenso pela administração no momento. '
        'Você receberá alertas quando ele for reativado.'
    )


def watch_not_found(ref: str) -> str:
    return (
        f'❌ Não encontrei o processo {ref} na pesquisa pública do SEI do CADE. '
        'Confira o número. Processos sigilosos não aparecem na pesquisa pública.'
    )


def watch_retrying(ref: str) -> str:
    return (
        f'⚠️ O SEI não respondeu ao consultar {ref}. Seu pedido está registrado e vou tentar '
        'de novo em alguns minutos.'
    )


def watch_gave_up(ref: str) -> str:
    return (
        f'⚠️ Ainda não consegui consultar {ref}: o SEI segue indisponível. '
        'O processo continua na sua lista; vou tentando na rotina normal e aviso aqui '
        'quando conseguir.'
    )


def unwatched(label: str) -> str:
    return f'Você não acompanha mais {label}.'


def list_empty() -> str:
    return f'Você ainda não acompanha nenhum processo. Comece com /watch {EXAMPLE}'


def list_items(items: list[tuple[str, bool, object]], limit: int) -> str:
    lines = [f'📋 Processos acompanhados ({len(items)}/{limit}):']
    for label, paused, checked_at in items:
        icon = '⏸️' if paused else '▶️'
        lines.append(f'{icon} {label} — verificado {fmt_dt(checked_at)}')
    return '\n'.join(lines)


def status(label: str, url: str, last_change, last_checked, records: list[str], paused: bool) -> str:
    change_line = (
        f'Última mudança detectada: {fmt_dt(last_change.detected_at)}\n{last_change.summary}'
        if last_change else 'Nenhuma mudança detectada desde que o monitoramento começou.'
    )
    paused_line = '\n⏸️ Alertas pausados para você.' if paused else ''
    return (
        f'📁 {label}\n'
        f'Última verificação: {fmt_dt(last_checked)}{paused_line}\n\n'
        f'{change_line}\n\n{latest_block(records)}\n\n🔗 {url}'
    )


def history(label: str, changes: list) -> str:
    if not changes:
        return f'Nenhuma movimentação nova registrada em {label} desde o início do monitoramento.'
    lines = [f'🗂️ Últimas movimentações de {label}:']
    for change in changes:
        lines.append(f'\n🕒 {fmt_dt(change.detected_at)}\n{change.summary}')
    return '\n'.join(lines)


def paused(label: str) -> str:
    return f'⏸️ Alertas de {label} pausados. Use /resume para retomar.'


def resumed(label: str) -> str:
    return f'▶️ Alertas de {label} retomados.'


def check_cooldown(label: str, last_checked, minutes_left: int, records: list[str]) -> str:
    return (
        f'{label} foi verificado há pouco ({fmt_dt(last_checked)}). '
        f'Você pode pedir nova verificação em {minutes_left} min.\n\n{latest_block(records)}'
    )


def check_queued(label: str) -> str:
    return f'🔎 Verificando {label} agora. Aviso aqui em instantes.'


def check_no_change(label: str, records: list[str]) -> str:
    return f'✅ Sem novidades em {label}.\n\n{latest_block(records)}'


def check_changed(label: str) -> str:
    # O alerta completo sai pelo fluxo normal de notificações, logo em seguida.
    return f'🔔 Encontrei movimentação nova em {label}! Os detalhes chegam no alerta a seguir.'


def check_failed(label: str) -> str:
    return f'⚠️ Não consegui consultar {label} agora (SEI indisponível). Tente mais tarde.'


def latest_queued(label: str) -> str:
    return f'📤 Preparando a última atualização de {label}, com o documento. Envio em instantes.'


def latest_no_data(label: str) -> str:
    return (
        f'Ainda não tenho a primeira leitura de {label}. '
        'Assim que ela sair, use /ultima de novo.'
    )


def latest_update(label: str, process_url: str, record: dict | None, doc_url: str, change, attachment_note: str) -> str:
    if record:
        parts = [record.get(k, '') for k in ('document', 'doc_type', 'doc_date')]
        doc_line = ' | '.join(p for p in parts if p)
        extra = ' | '.join(p for p in (
            f"Registro: {record['registry_date']}" if record.get('registry_date') else '',
            record.get('unit', ''),
        ) if p)
        doc_block = f'📄 Documento mais recente: {doc_line}' + (f'\n{extra}' if extra else '')
        doc_block += f'\n🔗 {doc_url}' if doc_url else '\n🔗 Link do documento não disponível.'
    else:
        doc_block = '📄 Não identifiquei documentos na Lista de Protocolos.'
    change_block = (
        f'📝 Última mudança detectada em {fmt_dt(change.detected_at)}:\n{change.summary}'
        if change else '📝 Nenhuma mudança detectada desde o início do monitoramento.'
    )
    note = f'\n\n📎 {attachment_note}' if attachment_note else ''
    return (
        f'📣 Última atualização de {label}\n\n{doc_block}\n\n{change_block}{note}'
        f'\n\n🔗 Processo no SEI/CADE:\n{process_url}'
    )
