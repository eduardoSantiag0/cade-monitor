
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from . import db
from .config import Config
from .env import update_env_file
from .monitor import check_process
from .notifiers import send_email
from .scraper import CADE_SEARCH_URL, is_url_source, latest_cade_records
from .utils import h, parse_recipients


CSS = '''
:root {
  color-scheme: light;
  --bg: #f3f6f8;
  --surface: #ffffff;
  --surface-soft: #f8fafc;
  --ink: #19212a;
  --muted: #607083;
  --line: #dce3ea;
  --brand: #0f766e;
  --brand-dark: #134e4a;
  --accent: #2f5aa8;
  --warning: #b7791f;
  --danger: #b42318;
  --success: #067647;
  --shadow: 0 10px 24px rgba(25, 33, 42, .08);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); }
header { background: #ffffff; border-bottom: 1px solid var(--line); }
.topbar { width: min(1320px, calc(100% - 32px)); margin: 0 auto; padding: 18px 0; display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.brand-mark { width: 38px; height: 38px; border-radius: 8px; display: grid; place-items: center; background: var(--brand); color: #fff; font-weight: 800; letter-spacing: 0; }
.brand h1 { margin: 0; font-size: 22px; letter-spacing: 0; line-height: 1.1; }
.brand p { margin: 3px 0 0; color: var(--muted); font-size: 13px; }
.header-meta { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.meta-pill { border: 1px solid var(--line); background: var(--surface-soft); border-radius: 999px; padding: 6px 10px; color: #334155; font-size: 12px; font-weight: 700; white-space: nowrap; }
.meta-pill.nav-link { text-decoration: none; }
.meta-pill.nav-link:hover { border-color: var(--brand); color: var(--brand-dark); }
main { width: min(1320px, calc(100% - 32px)); margin: 22px auto 56px; }
section { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 18px; margin-bottom: 18px; box-shadow: var(--shadow); }
.section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
h2 { margin: 0; font-size: 17px; letter-spacing: 0; }
.section-head p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
label { display: block; font-size: 12px; font-weight: 750; margin-bottom: 6px; color: #334155; }
input, textarea, select { width: 100%; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px 11px; font: inherit; background: #fff; color: var(--ink); }
input:focus, textarea:focus, select:focus { outline: 3px solid rgba(15, 118, 110, .16); border-color: var(--brand); }
textarea { min-height: 78px; resize: vertical; }
button, .button { border: 0; border-radius: 6px; padding: 9px 12px; background: var(--brand); color: #fff; font-weight: 750; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 38px; }
button:hover, .button:hover { filter: brightness(.96); }
button.secondary, .button.secondary { background: var(--accent); }
button.warn { background: var(--danger); }
button.light, .button.light { background: #eef4f7; color: #263442; border: 1px solid #cbd5e1; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.grid.three { grid-template-columns: 1.2fr 1.2fr .65fr; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.actions form { margin: 0; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.stat { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 14px; box-shadow: var(--shadow); }
.stat small { display: block; color: var(--muted); font-size: 12px; font-weight: 750; margin-bottom: 5px; }
.stat strong { display: block; font-size: 22px; line-height: 1.1; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
table { width: 100%; border-collapse: collapse; background: #fff; }
th, td { text-align: left; border-bottom: 1px solid #e5e7eb; padding: 11px 10px; vertical-align: top; }
th { background: #f8fafc; font-size: 11px; color: #526173; text-transform: uppercase; letter-spacing: .04em; }
tr:last-child td { border-bottom: 0; }
tr:hover td { background: #fbfdff; }
small, .muted { color: var(--muted); }
.status { display: inline-flex; border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 800; }
.status.ok { background: #dcfae6; color: var(--success); }
.status.wait { background: #fef3c7; color: #92400e; }
.status.err { background: #fee4e2; color: var(--danger); }
.status.sent { background: #dcfae6; color: var(--success); }
.status.failed { background: #fee4e2; color: var(--danger); }
.status.skipped { background: #fef3c7; color: #92400e; }
.flash { border-radius: 6px; padding: 11px 12px; margin-bottom: 16px; font-weight: 650; }
.flash.ok { background: #e7f8ee; border: 1px solid #b8ebc8; }
.flash.err { background: #fff1f1; border: 1px solid #ffc9c9; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #111827; color: #e5e7eb; padding: 12px; border-radius: 6px; font-size: 13px; }
.url { overflow-wrap: anywhere; max-width: 330px; }
.latest-records { margin: 0; padding-left: 18px; }
.latest-records li { margin-bottom: 6px; line-height: 1.35; }
.latest-records.compact { font-size: 13px; max-width: 420px; }
.detail-top { display: flex; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
.movement-block { border-top: 1px solid var(--line); padding: 14px 0; }
.movement-block:first-child { border-top: 0; padding-top: 0; }
.movement-block h3 { margin: 0 0 8px; font-size: 14px; }
@media (max-width: 980px) { .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } .grid, .grid.three { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .topbar { align-items: flex-start; flex-direction: column; } .header-meta { justify-content: flex-start; } .stats { grid-template-columns: 1fr; } table, thead, tbody, tr, td, th { display: block; } thead { display: none; } td { border-bottom: 0; padding: 7px 0; } tr { border-bottom: 1px solid #e5e7eb; padding: 10px; } .table-wrap { border: 0; } }
'''



def csrf_token(cfg: Config) -> str:
    return hmac.new(cfg.app_secret_key.encode('utf-8'), b'cade-monitor-forms', hashlib.sha256).hexdigest()


def hidden_csrf(cfg: Config) -> str:
    return f'<input type="hidden" name="csrf" value="{csrf_token(cfg)}">'


def render_layout(title: str, body: str) -> str:
    return f'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h(title)} - Meskade</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="topbar">
    <div class="brand">
      <div class="brand-mark">M</div>
      <div>
        <h1>Meskade</h1>
        <p>Monitoramento de processos CADE/SEI com alertas operacionais.</p>
      </div>
    </div>
    <div class="header-meta">
      <span class="meta-pill">CADE/SEI</span>
      <span class="meta-pill">E-mail</span>
      <span class="meta-pill">WhatsApp opcional</span>
      <a class="meta-pill nav-link" href="/settings">Configuracoes</a>
    </div>
  </div>
</header>
<main>{body}</main>
</body>
</html>'''


def flash_from_query(query: dict[str, list[str]]) -> str:
    if 'ok' in query:
        return f'<div class="flash ok">{h(query["ok"][0])}</div>'
    if 'error' in query:
        return f'<div class="flash err">{h(query["error"][0])}</div>'
    return ''


def status_badge(process) -> str:
    if process['last_error']:
        return f'<span class="status err">erro</span><br><small>{h(process["last_error"])}</small>'
    if not process['last_hash']:
        return '<span class="status wait">aguardando 1a leitura</span>'
    return '<span class="status ok">monitorando</span>'



def render_latest_records(last_text: str | None, compact: bool = False) -> str:
    records = latest_cade_records(last_text, 3)
    if not last_text:
        return '<small>Aguardando primeira leitura do CADE.</small>'
    if not records:
        return '<small>Nao foi possivel identificar andamentos/documentos na ultima leitura.</small>'
    class_name = 'latest-records compact' if compact else 'latest-records'
    items = ''.join(f'<li>{h(record)}</li>' for record in records)
    return f'<ol class="{class_name}">{items}</ol>'


def notification_badge(status: str) -> str:
    clean = status if status in {'sent', 'failed', 'skipped'} else 'failed'
    labels = {'sent': 'enviado', 'failed': 'falhou', 'skipped': 'ignorado'}
    return f'<span class="status {clean}">{labels.get(clean, h(status))}</span>'


def render_notifications_table(notifications) -> str:
    if not notifications:
        return '<small>Nenhuma tentativa de notificacao registrada ainda.</small>'
    rows = []
    for notification in notifications:
        error = notification['error'] or ''
        rows.append(f'''
<tr>
  <td>{h(notification['sent_at'])}<br><small>Movimento: {h(notification['detected_at'])}</small></td>
  <td>{h(notification['channel'])}</td>
  <td>{h(notification['destination'])}</td>
  <td>{notification_badge(notification['status'])}</td>
  <td><small>{h(error or '-')}</small></td>
</tr>''')
    return f'''
<div class="table-wrap">
  <table>
    <thead><tr><th>Quando</th><th>Canal</th><th>Destino</th><th>Status</th><th>Erro</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>'''


def build_test_email(process, movement) -> tuple[str, str]:
    subject = f'[Meskade] Teste de alerta: {process["label"]}'[:180]
    latest = latest_cade_records(process['last_text'], 3)
    latest_block = '\n'.join(f'- {record}' for record in latest) or '- Nenhum registro estruturado encontrado na ultima leitura.'
    if movement:
        movement_block = f"Ultima movimentacao registrada pelo Meskade:\n{movement['summary']}\n\nDetalhes:\n{movement['diff']}"
    else:
        movement_block = 'Nenhuma movimentacao historica registrada pelo Meskade ainda. Este teste usa apenas a ultima leitura salva.'
    body = (
        'Este e um e-mail de teste do Meskade.\n\n'
        f'Processo: {process["label"]}\n'
        f'Origem: {process["public_url"]}\n\n'
        f'{movement_block}\n\n'
        f'Ultimos registros vistos no CADE:\n{latest_block}\n\n'
        'Se este e-mail chegou, o SMTP esta funcionando para este destinatario.'
    )
    return subject, body


def send_test_email_for_process(conn, cfg: Config, process_id: int) -> tuple[bool, str]:
    process = db.get_process(conn, process_id)
    if process is None:
        return False, 'Processo nao encontrado.'
    email_subscribers = [subscriber for subscriber in db.enabled_subscribers(conn, process_id) if subscriber['channel'] == 'email']
    if not email_subscribers:
        return False, 'Nenhum assinante de e-mail ativo neste processo.'

    latest_movement = None
    movements = db.recent_movements(conn, process_id, 1)
    if movements:
        latest_movement = movements[0]
    subject, body = build_test_email(process, latest_movement)

    sent = failed = skipped = 0
    errors: list[str] = []
    for subscriber in email_subscribers:
        status, error = send_email(cfg, subscriber['destination'], subject, body)
        if latest_movement:
            db.record_notification(
                conn,
                latest_movement['id'],
                subscriber['id'],
                'email',
                subscriber['destination'],
                status,
                error,
            )
        if status == 'sent':
            sent += 1
        elif status == 'skipped':
            skipped += 1
            if error:
                errors.append(f"{subscriber['destination']}: {error}")
        else:
            failed += 1
            if error:
                errors.append(f"{subscriber['destination']}: {error}")

    ok = sent > 0 and failed == 0 and skipped == 0
    message = f'Teste de e-mail: {sent} enviado(s), {failed} falha(s), {skipped} ignorado(s).'
    if errors:
        message += ' ' + ' | '.join(errors[:2])
    return ok, message


def checked(value: bool) -> str:
    return 'checked' if value else ''


def selected(current: str, option: str) -> str:
    return 'selected' if current == option else ''


def env_setting(name: str, default: str = '') -> str:
    return os.getenv(name, default)


def secret_placeholder(value: str) -> str:
    return 'valor atual mantido se ficar em branco' if value else ''


def render_settings(cfg: Config, query: dict[str, list[str]]) -> str:
    provider = cfg.whatsapp_provider
    return render_layout('Configuracoes', f'''
{flash_from_query(query)}
<section>
  <div class="section-head">
    <div>
      <h2>Configuracoes de envio</h2>
      <p>Edite o SMTP, remetente e integracoes de WhatsApp usados nos alertas.</p>
    </div>
    <a class="button light" href="/">Voltar</a>
  </div>
  <form method="post" action="/settings">
    {hidden_csrf(cfg)}
    <h2 style="margin:6px 0 12px">E-mail</h2>
    <div class="grid three">
      <div><label>Servidor SMTP</label><input name="SMTP_HOST" value="{h(cfg.mail_host)}" placeholder="smtp.example.com"></div>
      <div><label>Porta SMTP</label><input name="SMTP_PORT" type="number" min="1" max="65535" value="{h(cfg.mail_port)}"></div>
      <div><label>Usuario SMTP</label><input name="SMTP_USER" value="{h(cfg.mail_user)}" placeholder="usuario@example.com"></div>
    </div>
    <div class="grid" style="margin-top:14px">
      <div><label>Senha SMTP</label><input name="SMTP_PASSWORD" type="password" placeholder="{h(secret_placeholder(cfg.mail_password))}"></div>
      <div><label>Remetente</label><input name="MAIL_FROM" value="{h(cfg.mail_from)}" placeholder="Meskade &lt;alertas@dominio.com.br&gt;"></div>
    </div>
    <div class="actions" style="margin-top:12px">
      <label style="display:inline-flex;align-items:center;gap:8px;margin:0"><input style="width:auto" type="checkbox" name="SMTP_TLS" value="true" {checked(cfg.mail_tls)}> TLS</label>
      <label style="display:inline-flex;align-items:center;gap:8px;margin:0"><input style="width:auto" type="checkbox" name="SMTP_SSL" value="true" {checked(cfg.mail_ssl)}> SSL direto</label>
    </div>

    <h2 style="margin:24px 0 12px">WhatsApp (Evolution)</h2>
    <div class="grid three">
      <div>
        <label>Provedor</label>
        <select name="WHATSAPP_PROVIDER">
          <option value="" {selected(provider, '')}>Desativado</option>
          <option value="evolution" {selected(provider, 'evolution')}>Evolution API</option>
        </select>
      </div>
      <div><label>URL da Evolution API</label><input name="EVOLUTION_API_BASE_URL" value="{h(cfg.evolution_api_base_url)}" placeholder="http://localhost:8080"></div>
      <div><label>Nome da instancia</label><input name="EVOLUTION_INSTANCE_NAME" value="{h(cfg.evolution_instance_name)}" placeholder="cade-monitor"></div>
    </div>
    <div class="grid" style="margin-top:14px">
      <div><label>API Key</label><input name="EVOLUTION_API_KEY" type="password" placeholder="{h(secret_placeholder(cfg.evolution_api_key))}"></div>
      <div><label>Timeout (segundos)</label><input name="EVOLUTION_TIMEOUT_SECONDS" type="number" min="5" max="120" value="{h(cfg.evolution_timeout_seconds)}"></div>
    </div>
    <div class="actions" style="margin-top:12px">
      <label style="display:inline-flex;align-items:center;gap:8px;margin:0"><input style="width:auto" type="checkbox" name="EVOLUTION_ENABLED" value="true" {checked(cfg.evolution_enabled)}> Evolution habilitada</label>
    </div>

    <div class="actions" style="margin-top:18px"><button>Salvar configuracoes</button></div>
  </form>
</section>
''')


def settings_updates_from_form(form: dict[str, list[str]], cfg: Config) -> dict[str, str]:
    def field(name: str, default: str = '') -> str:
        return form.get(name, [default])[0].strip()

    provider = field('WHATSAPP_PROVIDER').lower()
    if provider not in {'', 'evolution'}:
        raise ValueError('Provedor de WhatsApp invalido.')

    smtp_port = field('SMTP_PORT', str(cfg.mail_port or 587)) or '587'
    evolution_timeout = field('EVOLUTION_TIMEOUT_SECONDS', str(cfg.evolution_timeout_seconds or 15)) or '15'
    for label, value in {'Porta SMTP': smtp_port, 'Timeout da Evolution': evolution_timeout}.items():
        try:
            port = int(value)
        except ValueError as exc:
            raise ValueError(f'{label} precisa ser numerica.') from exc
      if label == 'Porta SMTP' and (port < 1 or port > 65535):
        raise ValueError('Porta SMTP precisa estar entre 1 e 65535.')
      if label == 'Timeout da Evolution' and (port < 5 or port > 120):
        raise ValueError('Timeout da Evolution precisa estar entre 5 e 120 segundos.')

    updates = {
        'SMTP_HOST': field('SMTP_HOST'),
        'SMTP_PORT': smtp_port,
        'SMTP_USER': field('SMTP_USER'),
        'MAIL_FROM': field('MAIL_FROM'),
        'SMTP_TLS': 'true' if 'SMTP_TLS' in form else 'false',
        'SMTP_SSL': 'true' if 'SMTP_SSL' in form else 'false',
        'WHATSAPP_PROVIDER': provider,
        'EVOLUTION_ENABLED': 'true' if 'EVOLUTION_ENABLED' in form else 'false',
        'EVOLUTION_API_BASE_URL': field('EVOLUTION_API_BASE_URL', cfg.evolution_api_base_url),
        'EVOLUTION_INSTANCE_NAME': field('EVOLUTION_INSTANCE_NAME', cfg.evolution_instance_name),
        'EVOLUTION_TIMEOUT_SECONDS': evolution_timeout,
    }

    secret_defaults = {
        'SMTP_PASSWORD': cfg.mail_password,
        'EVOLUTION_API_KEY': cfg.evolution_api_key,
    }
    for key, current in secret_defaults.items():
        submitted = field(key)
        updates[key] = submitted if submitted else current

    return updates


def origin_cell(source: str) -> str:
    if is_url_source(source):
        return f'<td class="url"><a href="{h(source)}" target="_blank" rel="noreferrer">Pagina publica CADE</a><br><small>{h(source)}</small></td>'
    return f'<td class="url"><strong>{h(source)}</strong><br><small><a href="{h(CADE_SEARCH_URL)}" target="_blank" rel="noreferrer">Pesquisa publica CADE</a></small></td>'


def render_dashboard(cfg: Config, conn, query: dict[str, list[str]]) -> str:
    processes = db.list_processes(conn)
    total_count = len(processes)
    active_count = sum(1 for process in processes if process['enabled'])
    error_count = sum(1 for process in processes if process['last_error'])
    changed_count = sum(1 for process in processes if process['movement_count'])
    rows = []
    for process in processes:
        enabled = 'ativo' if process['enabled'] else 'pausado'
        rows.append(f'''
<tr>
  <td><strong>{h(process['label'])}</strong><br><small>#{process['id']} - {enabled}</small></td>
  {origin_cell(process['public_url'])}
  <td>{status_badge(process)}</td>
  <td><small>Ultima checagem: {h(process['last_checked_at'] or '-')}<br>Ultima mudanca: {h(process['last_changed_at'] or '-')}<br>Mov.: {h(process['movement_count'])} - Assinantes: {h(process['subscriber_count'])}</small></td>
  <td>{render_latest_records(process['last_text'], compact=True)}</td>
  <td>
    <div class="actions">
      <a class="button light" href="/processes/{process['id']}">Abrir</a>
      <form method="post" action="/processes/{process['id']}/check">{hidden_csrf(cfg)}<button class="secondary">Checar</button></form>
      <form method="post" action="/processes/{process['id']}/toggle">{hidden_csrf(cfg)}<button class="light">Pausar/ativar</button></form>
      <form method="post" action="/processes/{process['id']}/delete" onsubmit="return confirm('Excluir este monitor?')">{hidden_csrf(cfg)}<button class="warn">Excluir</button></form>
    </div>
  </td>
</tr>''')

    mail_state = 'configurado' if cfg.mail_host and cfg.mail_from else 'pendente'
    wa_state = cfg.whatsapp_provider or 'pendente'
    table = ''.join(rows) if rows else '<tr><td colspan="6"><small>Nenhum processo cadastrado ainda.</small></td></tr>'
    return render_layout('Painel', f'''
{flash_from_query(query)}
<div class="stats">
  <div class="stat"><small>Processos</small><strong>{h(total_count)}</strong></div>
  <div class="stat"><small>Ativos</small><strong>{h(active_count)}</strong></div>
  <div class="stat"><small>Com movimentacao</small><strong>{h(changed_count)}</strong></div>
  <div class="stat"><small>Erros de leitura</small><strong>{h(error_count)}</strong></div>
</div>
<section>
  <div class="section-head">
    <div>
      <h2>Novo monitor</h2>
      <p>Cadastre o link publico do processo ou o numero SEI para iniciar a linha de base. Intervalo minimo: 25 minutos.</p>
    </div>
    <div class="header-meta"><span class="meta-pill">E-mail: {h(mail_state)}</span><span class="meta-pill">WhatsApp: {h(wa_state)}</span></div>
  </div>
  <form method="post" action="/processes">
    {hidden_csrf(cfg)}
    <div class="grid">
      <div><label>Nome interno</label><input name="label" placeholder="Ex.: P. Samba - 08700..." required></div>
      <div><label>URL publica ou numero do processo/protocolo</label><input name="public_url" placeholder="https://sei.cade.gov.br/... ou 08700.005905/2026-38" required></div>
    </div>
    <div class="grid three" style="margin-top:14px">
      <div><label>E-mails, separados por virgula</label><textarea name="emails" placeholder="vmesquita@pn.com.br"></textarea></div>
      <div><label>WhatsApp, separados por virgula</label><textarea name="phones" placeholder="+5511999999999"></textarea></div>
      <div><label>Intervalo em minutos</label><input name="interval_minutes" type="number" min="25" value="{cfg.poll_interval_minutes}"></div>
    </div>
    <div class="actions" style="margin-top:14px"><button>Cadastrar monitor</button></div>
  </form>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>Processos monitorados</h2>
      <p>Acompanhe a ultima leitura salva, notificacoes e registros recentes vistos no CADE.</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Processo</th><th>Origem monitorada</th><th>Status</th><th>Historico</th><th>Ultimos vistos</th><th>Acoes</th></tr></thead>
      <tbody>{table}</tbody>
    </table>
  </div>
</section>
''')

def render_process_detail(cfg: Config, conn, process_id: int, query: dict[str, list[str]]) -> str:
    process = db.get_process(conn, process_id)
    if process is None:
        return render_layout('Nao encontrado', '<section><h2>Processo nao encontrado</h2><a class="button light" href="/">Voltar</a></section>')
    source_href = process['public_url'] if is_url_source(process['public_url']) else CADE_SEARCH_URL
    source_label = 'Pagina oficial' if is_url_source(process['public_url']) else 'Pesquisa publica CADE'
    subscribers = db.get_subscribers(conn, process_id)
    movements = db.recent_movements(conn, process_id, 30)
    notifications = db.recent_notifications(conn, process_id, 30)
    sub_rows = []
    for subscriber in subscribers:
        sub_rows.append(f'''
<tr>
  <td>{h(subscriber['channel'])}</td>
  <td>{h(subscriber['destination'])}</td>
  <td><form method="post" action="/subscribers/{subscriber['id']}/delete">{hidden_csrf(cfg)}<button class="warn">Remover</button></form></td>
</tr>''')
    mov_blocks = []
    for movement in movements:
        mov_blocks.append(f'''
<div class="movement-block">
  <h3>{h(movement['detected_at'])}</h3>
  <p>{h(movement['summary'])}</p>
  <pre>{h(movement['diff'])}</pre>
</div>''')
    return render_layout(h(process['label']), f'''
{flash_from_query(query)}
<section>
  <div class="detail-top">
    <div>
      <div class="actions"><a class="button light" href="/">Voltar</a><a class="button light" href="{h(source_href)}" target="_blank" rel="noreferrer">{h(source_label)}</a><form method="post" action="/processes/{process_id}/test-email">{hidden_csrf(cfg)}<button class="secondary">Enviar e-mail teste</button></form></div>
      <h2 style="margin-top:14px">{h(process['label'])}</h2>
      <p class="url"><small>Origem: {h(process['public_url'])}</small></p>
    </div>
    <div>{status_badge(process)}</div>
  </div>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>Ultimos registros vistos no CADE</h2>
      <p>Fonte: ultima leitura salva do processo. Use Checar para atualizar agora.</p>
    </div>
  </div>
  {render_latest_records(process['last_text'])}
</section>
<section>
  <div class="section-head">
    <div>
      <h2>Assinantes</h2>
      <p>Destinatarios cadastrados para receber alertas deste processo.</p>
    </div>
  </div>
  <form method="post" action="/processes/{process_id}/subscribers">
    {hidden_csrf(cfg)}
    <div class="grid three">
      <div><label>Canal</label><select name="channel"><option value="email">E-mail</option><option value="whatsapp">WhatsApp</option></select></div>
      <div><label>Destino</label><input name="destination" placeholder="email ou +5511999999999" required></div>
      <div><label>&nbsp;</label><button>Adicionar</button></div>
    </div>
  </form>
  <div class="table-wrap" style="margin-top:14px"><table><thead><tr><th>Canal</th><th>Destino</th><th></th></tr></thead><tbody>{''.join(sub_rows) or '<tr><td colspan="3"><small>Nenhum assinante.</small></td></tr>'}</tbody></table></div>
</section>
<section>
  <div class="section-head"><div><h2>Notificacoes recentes</h2><p>Resultado das ultimas tentativas de envio.</p></div></div>
  {render_notifications_table(notifications)}
</section>
<section>
  <div class="section-head"><div><h2>Movimentacoes detectadas</h2><p>Historico de mudancas registradas pelo Meskade.</p></div></div>
  {''.join(mov_blocks) or '<small>Nenhuma movimentacao registrada depois da linha de base.</small>'}
</section>
''')


class CadeHandler(BaseHTTPRequestHandler):
    server: 'CadeServer'

    def log_message(self, fmt: str, *args) -> None:
        print('%s - %s' % (self.address_string(), fmt % args))

    @property
    def cfg(self) -> Config:
        return self.server.cfg

    def authenticated(self) -> bool:
        header = self.headers.get('Authorization', '')
        if not header.startswith('Basic '):
            return False
        try:
            decoded = base64.b64decode(header.split(' ', 1)[1]).decode('utf-8')
            username, password = decoded.split(':', 1)
        except Exception:
            return False
        return hmac.compare_digest(username, self.cfg.admin_user) and hmac.compare_digest(password, self.cfg.admin_password)

    def require_auth(self) -> bool:
        if self.authenticated():
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Meskade"')
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b'Autenticacao necessaria')
        return False

    def send_html(self, html: str, status: int = 200) -> None:
        data = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header('Location', location)
        self.end_headers()

    def form(self) -> dict[str, list[str]]:
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length).decode('utf-8')
        return parse_qs(raw, keep_blank_values=True)

    def validate_csrf(self, form: dict[str, list[str]]) -> bool:
        token = form.get('csrf', [''])[0]
        return hmac.compare_digest(token, csrf_token(self.cfg))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == '/healthz':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
            return
        if not self.require_auth():
            return
        conn = db.connect(self.cfg.db_path)
        try:
            query = parse_qs(parsed.query)
            if parsed.path == '/':
                self.send_html(render_dashboard(self.cfg, conn, query))
                return
            if parsed.path == '/settings':
                self.send_html(render_settings(self.cfg, query))
                return
            match = re.match(r'^/processes/(\d+)$', parsed.path)
            if match:
                self.send_html(render_process_detail(self.cfg, conn, int(match.group(1)), query))
                return
            self.send_html(render_layout('Nao encontrado', '<section><h2>Pagina nao encontrada</h2></section>'), 404)
        finally:
            conn.close()

    def do_POST(self) -> None:
        if not self.require_auth():
            return
        form = self.form()
        if not self.validate_csrf(form):
            self.redirect('/?error=' + quote('Sessao invalida. Recarregue a pagina.'))
            return
        conn = db.connect(self.cfg.db_path)
        parsed = urlparse(self.path)
        try:
            try:
                self.handle_post(conn, parsed.path, form)
            except Exception as exc:
                target = '/settings' if parsed.path == '/settings' else '/'
                self.redirect(target + '?error=' + quote(str(exc)))
        finally:
            conn.close()

    def handle_post(self, conn, path: str, form: dict[str, list[str]]) -> None:
        if path == '/settings':
            updates = settings_updates_from_form(form, self.cfg)
            update_env_file(self.cfg.env_path, updates)
            for key, value in updates.items():
                os.environ[key] = value
            self.server.cfg = Config.from_env()
            self.redirect('/settings?ok=' + quote('Configuracoes salvas. Reinicie worker e WhatsApp para aplicar nos envios automaticos.'))
            return
        if path == '/processes':
            label = form.get('label', [''])[0]
            public_url = form.get('public_url', [''])[0]
            emails = parse_recipients(form.get('emails', [''])[0])
            phones = parse_recipients(form.get('phones', [''])[0])
            raw_interval = form.get('interval_minutes', form.get('interval', [self.cfg.poll_interval_minutes]))[0]
            interval_minutes = max(25, int(raw_interval or self.cfg.poll_interval_minutes))
            process_id = db.add_process(conn, label, public_url, emails, phones, interval_minutes * 60)
            self.redirect(f'/processes/{process_id}?ok=' + quote('Monitor cadastrado. Use Checar para gravar a primeira leitura ou aguarde o worker.'))
            return
        match = re.match(r'^/processes/(\d+)/(check|delete|toggle|subscribers|test-email)$', path)
        if match:
            process_id = int(match.group(1))
            action = match.group(2)
            if action == 'check':
                result = check_process(conn, self.cfg, process_id)
                target = f'/processes/{process_id}'
                key = 'ok' if result.get('ok') else 'error'
                self.redirect(target + '?' + key + '=' + quote(result.get('message', 'Concluido')))
                return
            if action == 'test-email':
                ok, message = send_test_email_for_process(conn, self.cfg, process_id)
                key = 'ok' if ok else 'error'
                self.redirect(f'/processes/{process_id}?' + key + '=' + quote(message))
                return
            if action == 'delete':
                db.delete_process(conn, process_id)
                self.redirect('/?ok=' + quote('Monitor excluido.'))
                return
            if action == 'toggle':
                db.toggle_process(conn, process_id)
                self.redirect('/?ok=' + quote('Status atualizado.'))
                return
            if action == 'subscribers':
                channel = form.get('channel', ['email'])[0]
                destination = form.get('destination', [''])[0]
                db.add_subscriber(conn, process_id, channel, destination)
                conn.commit()
                self.redirect(f'/processes/{process_id}?ok=' + quote('Assinante adicionado.'))
                return
        match = re.match(r'^/subscribers/(\d+)/delete$', path)
        if match:
            subscriber_id = int(match.group(1))
            db.delete_subscriber(conn, subscriber_id)
            self.redirect('/?ok=' + quote('Assinante removido.'))
            return
        self.redirect('/?error=' + quote('Acao nao encontrada.'))


class CadeServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], cfg: Config):
        self.cfg = cfg
        super().__init__(address, CadeHandler)


def run_server(cfg: Config, host: str, port: int) -> None:
    server = CadeServer((host, port), cfg)
    print(f'Meskade web em http://{host}:{port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Meskade web encerrado.')
    finally:
        server.server_close()
