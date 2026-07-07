const http = require('http');
const path = require('path');
const qrcode = require('qrcode-terminal');
const pino = require('pino');
const {
  default: makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys');

const PORT = Number(process.env.WHATSAPP_WEBBOT_PORT || 18188);
const TOKEN = process.env.WHATSAPP_WEBBOT_TOKEN || '';
const AUTH_DIR = process.env.WHATSAPP_WEBBOT_AUTH_DIR || path.join(__dirname, '..', 'data', 'wa-auth');
const MAX_BODY_BYTES = Number(process.env.WHATSAPP_WEBBOT_MAX_BODY_BYTES || 32 * 1024 * 1024);

let sock = null;
let connected = false;
let connecting = false;

function log(message) {
  console.log(new Date().toISOString(), message);
}

function phoneCandidates(destination) {
  const digits = String(destination || '').replace(/\D/g, '');
  if (!digits) throw new Error('Destino WhatsApp invalido');
  const candidates = [digits];
  if (digits.startsWith('55') && digits.length === 13 && digits[4] === '9') {
    candidates.push(digits.slice(0, 4) + digits.slice(5));
  }
  if (digits.startsWith('55') && digits.length === 12) {
    candidates.push(digits.slice(0, 4) + '9' + digits.slice(4));
  }
  return [...new Set(candidates)];
}

async function resolveJid(destination) {
  const raw = String(destination || '').trim();
  if (raw.endsWith('@s.whatsapp.net') || raw.endsWith('@g.us')) {
    return raw;
  }

  const candidates = phoneCandidates(destination);
  for (const candidate of candidates) {
    const matches = await sock.onWhatsApp(candidate);
    const found = Array.isArray(matches) ? matches.find((item) => item && item.exists && item.jid) : null;
    if (found) {
      log('Destino WhatsApp resolvido: ' + candidate + ' -> ' + found.jid);
      return found.jid;
    }
  }

  const fallback = candidates[0] + '@s.whatsapp.net';
  log('WhatsApp nao confirmou o destino; tentando fallback: ' + fallback);
  return fallback;
}

async function startSocket() {
  if (connecting) return;
  connecting = true;
  try {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();
    sock = makeWASocket({
      auth: state,
      version,
      printQRInTerminal: false,
      logger: pino({ level: process.env.WHATSAPP_WEBBOT_LOG_LEVEL || 'silent' }),
      browser: ['Meskade', 'Chrome', '1.0.0'],
    });

    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('connection.update', (update) => {
      const { connection, lastDisconnect, qr } = update;
      if (qr) {
        log('Escaneie este QR Code no WhatsApp > Dispositivos conectados:');
        qrcode.generate(qr, { small: true });
      }
      if (connection === 'open') {
        connected = true;
        log('WhatsApp conectado.');
      }
      if (connection === 'close') {
        connected = false;
        const statusCode = lastDisconnect && lastDisconnect.error && lastDisconnect.error.output && lastDisconnect.error.output.statusCode;
        log('WhatsApp desconectado. status=' + (statusCode || 'desconhecido'));
        if (statusCode !== DisconnectReason.loggedOut) {
          setTimeout(() => startSocket().catch((error) => log('Erro reconectando: ' + error.message)), 5000);
        } else {
          log('Sessao encerrada. Apague ' + AUTH_DIR + ' e escaneie o QR novamente.');
        }
      }
    });
  } finally {
    connecting = false;
  }
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error('Payload muito grande'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => {
      try {
        const raw = Buffer.concat(chunks).toString('utf8') || '{}';
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(new Error('JSON invalido'));
      }
    });
    req.on('error', reject);
  });
}

function sendJson(res, status, payload) {
  const body = Buffer.from(JSON.stringify(payload));
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': body.length,
  });
  res.end(body);
}

async function handleSend(req, res) {
  if (TOKEN && req.headers['x-meskade-token'] !== TOKEN) {
    sendJson(res, 401, { ok: false, error: 'Token invalido' });
    return;
  }
  if (!connected || !sock) {
    sendJson(res, 503, { ok: false, error: 'WhatsApp ainda nao conectado. Veja logs/whatsapp.log e escaneie o QR.' });
    return;
  }

  const payload = await readJson(req);
  const jid = await resolveJid(payload.to);
  const body = String(payload.body || '').slice(0, 3900);
  const attachments = Array.isArray(payload.attachments) ? payload.attachments.slice(0, 3) : [];

  if (body) {
    await sock.sendMessage(jid, { text: body });
  }

  for (const attachment of attachments) {
    const filename = String(attachment.filename || 'documento.pdf').slice(0, 140);
    const mimetype = String(attachment.content_type || 'application/octet-stream');
    const contentBase64 = String(attachment.content_base64 || '');
    if (!contentBase64) continue;
    const buffer = Buffer.from(contentBase64, 'base64');
    await sock.sendMessage(jid, {
      document: buffer,
      fileName: filename,
      mimetype,
      caption: 'Documento novo no Meskade: ' + filename,
    });
  }

  log('Mensagem enviada para ' + jid + '; anexos=' + attachments.length);
  sendJson(res, 200, { ok: true, jid, sent_attachments: attachments.length });
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === 'GET' && req.url === '/healthz') {
      sendJson(res, connected ? 200 : 503, { ok: connected, connected });
      return;
    }
    if (req.method === 'POST' && req.url === '/send') {
      await handleSend(req, res);
      return;
    }
    sendJson(res, 404, { ok: false, error: 'Nao encontrado' });
  } catch (error) {
    sendJson(res, 500, { ok: false, error: error.message });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  log('Meskade WhatsApp WebBot em http://127.0.0.1:' + PORT);
  startSocket().catch((error) => log('Erro iniciando WhatsApp: ' + (error.stack || error.message)));
});