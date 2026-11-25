// WhatsApp linked-device bridge (UNOFFICIAL - Baileys). Listens on 127.0.0.1 only.
// It never starts chats, never bulk-sends and never reads contact lists. It only:
//  - shows a pairing QR, keeps the session (encrypted), reconnects;
//  - forwards incoming 1:1 messages to the backend;
//  - sends a reply when the backend asks.
import http from 'node:http'
import { rm } from 'node:fs/promises'
import { resolve } from 'node:path'
import makeWASocket, { DisconnectReason, downloadMediaMessage, fetchLatestBaileysVersion } from 'baileys'
import pino from 'pino'
import QRCode from 'qrcode'
import { useEncryptedAuthState } from './encryptedAuth.js'

const PORT = Number(process.env.BRIDGE_PORT || 8200)
const SECRET = process.env.BRIDGE_SECRET || ''
const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8100'
const SESSION_DIR = resolve(process.env.WA_SESSION_DIR || '../storage/whatsapp_sessions/default')
const SESSION_KEY = process.env.WA_SESSION_KEY || ''
if (SECRET.length < 32 || SESSION_KEY.length < 32) {
  console.error('BRIDGE_SECRET and WA_SESSION_KEY (32+ chars) are required')
  process.exit(1)
}

const log = pino({ level: process.env.LOG_LEVEL || 'warn' })
let sock = null
let state = { status: 'disconnected', qr: null, account: '', lastError: '', since: Date.now() }
let retries = 0
let wanted = false
const seen = new Set()
const typingSince = new Map()
// "online" only while answering, like a person opening WhatsApp; offline again ~20 s after the last reply
const ONLINE_GRACE_MS = 20000
let offlineTimer = null
async function goOnline () {
  clearTimeout(offlineTimer)
  await sock?.sendPresenceUpdate('available').catch(() => {})
}
function goOfflineLater () {
  clearTimeout(offlineTimer)
  offlineTimer = setTimeout(() => { sock?.sendPresenceUpdate('unavailable').catch(() => {}) }, ONLINE_GRACE_MS)
}
const sleep = ms => new Promise(r => setTimeout(r, ms))
// Natural pacing: a short reply appears after ~2 s, a long one after up to ~9 s (counted from when typing started).
const humanDelay = text => Math.min(9000, 1800 + text.length * 35)

const mask = id => (id ? `***${String(id).split('@')[0].split(':')[0].slice(-4)}` : '')
const setState = patch => { state = { ...state, ...patch, since: Date.now() }; postBackend('/api/wa/state', { status: state.status, account: state.account, error: state.lastError }) }

async function postBackend(path, body) {
  try {
    await fetch(`${BACKEND}${path}`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-bridge-secret': SECRET }, body: JSON.stringify(body) })
  } catch (e) {
    log.warn({ err: e?.message }, 'backend not reachable')
  }
}

function phoneOf(key) {
  // Baileys 7 may address users by LID; prefer the phone-number JID when present
  const alt = key.remoteJidAlt || key.senderPn || key.participantAlt
  const jid = alt && alt.endsWith('@s.whatsapp.net') ? alt : key.remoteJid
  return jid.split('@')[0].split(':')[0]
}

function textOf(m) {
  const msg = m.message || {}
  const inner = msg.ephemeralMessage?.message || msg.viewOnceMessage?.message || msg
  return inner.conversation || inner.extendedTextMessage?.text || inner.imageMessage?.caption || inner.videoMessage?.caption || ''
}

function typeOf(m) {
  const msg = m.message || {}
  const inner = msg.ephemeralMessage?.message || msg
  if (inner.conversation || inner.extendedTextMessage) return 'text'
  if (inner.imageMessage) return 'image'
  if (inner.audioMessage) return 'audio'
  if (inner.videoMessage) return 'video'
  if (inner.documentMessage || inner.documentWithCaptionMessage) return 'document'
  if (inner.stickerMessage) return 'sticker'
  return 'other'
}

// Declared size of an attached file, read from the message header (nothing is downloaded to find it).
const MAX_FILE_BYTES = 10 * 1024 * 1024
function fileSizeOf(m) {
  const msg = m.message || {}
  const inner = msg.ephemeralMessage?.message || msg.viewOnceMessage?.message || msg
  const media = inner.imageMessage || inner.audioMessage || inner.videoMessage || inner.documentMessage ||
    inner.documentWithCaptionMessage?.message?.documentMessage || inner.stickerMessage
  const len = media?.fileLength
  return len == null ? 0 : Number(len.toString())
}

async function connect() {
  wanted = true
  const { state: auth, saveCreds } = await useEncryptedAuthState(SESSION_DIR, SESSION_KEY)
  let version
  try { ({ version } = await fetchLatestBaileysVersion()) } catch { /* use built-in */ }
  setState({ status: 'connecting', lastError: '' })
  sock = makeWASocket({ auth, logger: log, version, printQRInTerminal: false, markOnlineOnConnect: false, syncFullHistory: false, browser: ['Local AI Agent', 'Desktop', '1.0'] })
  sock.ev.on('creds.update', saveCreds)
  sock.ev.on('connection.update', async u => {
    if (u.qr) setState({ status: 'qr', qr: await QRCode.toDataURL(u.qr, { margin: 1, width: 280 }) })
    if (u.connection === 'open') {
      retries = 0
      setState({ status: 'connected', qr: null, account: mask(sock.user?.id) })
    }
    if (u.connection === 'close') {
      const code = u.lastDisconnect?.error?.output?.statusCode
      if (code === DisconnectReason.loggedOut) {
        await rm(SESSION_DIR, { recursive: true, force: true })
        setState({ status: 'logged_out', qr: null, account: '', lastError: 'Logged out from the phone. Session deleted.' })
        wanted = false
        return
      }
      if (!wanted) return setState({ status: 'disconnected', qr: null })
      retries += 1
      const wait = Math.min(60, 2 ** retries) * 1000
      setState({ status: 'reconnecting', qr: null, lastError: `closed (code ${code ?? '?'}), retry in ${wait / 1000}s` })
      setTimeout(() => wanted && connect().catch(e => setState({ status: 'error', lastError: e.message })), wait)
    }
  })
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return
    for (const m of messages) {
      const jid = m.key.remoteJid || ''
      if (m.key.fromMe || !(jid.endsWith('@s.whatsapp.net') || jid.endsWith('@lid'))) continue  // 1:1 chats only
      if (!m.message || seen.has(m.key.id)) continue
      seen.add(m.key.id)
      if (seen.size > 5000) seen.clear()
      const kind = typeOf(m)
      const size = fileSizeOf(m)
      const event = { id: m.key.id, jid, from: phoneOf(m.key), name: m.pushName || '', type: kind,
        text: String(textOf(m)).slice(0, 4000), ts: Number(m.messageTimestamp) || 0, size }
      if (size > MAX_FILE_BYTES) {
        // Big file: never downloaded, never read, never stored. Only "a big file arrived" is reported.
        event.too_large = true
        event.text = ''
      } else if ((kind === 'image' || kind === 'audio') && process.env.MEDIA_ENABLED === '1') {
        try {
          const buf = await downloadMediaMessage(m, 'buffer', {}, { logger: log, reuploadRequest: sock.updateMediaMessage })
          if (buf.length <= MAX_FILE_BYTES) event.media = buf.toString('base64')
          else event.too_large = true
        } catch (e) { event.media_error = e?.message }
      }
      postBackend('/api/wa/event', event)
    }
  })
}

async function disconnect(logout) {
  wanted = false
  try { if (logout) await sock?.logout(); else sock?.end(undefined) } catch { /* already closed */ }
  sock = null
  if (logout) await rm(SESSION_DIR, { recursive: true, force: true })
  setState({ status: logout ? 'logged_out' : 'disconnected', qr: null, account: logout ? '' : state.account })
}

function body(req) {
  return new Promise((res, rej) => {
    let d = ''
    req.on('data', c => { d += c; if (d.length > 64 * 1024) { rej(new Error('too large')); req.destroy() } })
    req.on('end', () => { try { res(d ? JSON.parse(d) : {}) } catch (e) { rej(e) } })
  })
}

const server = http.createServer(async (req, res) => {
  const send = (code, obj) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(obj)) }
  if (req.headers['x-bridge-secret'] !== SECRET) return send(401, { error: 'unauthorized' })
  try {
    if (req.method === 'GET' && req.url === '/status') return send(200, state)
    if (req.method === 'POST' && req.url === '/connect') {
      if (!sock) connect().catch(e => setState({ status: 'error', lastError: e.message }))
      return send(200, { ok: true })
    }
    if (req.method === 'POST' && req.url === '/disconnect') { await disconnect(false); return send(200, { ok: true }) }
    if (req.method === 'POST' && req.url === '/logout') { await disconnect(true); return send(200, { ok: true }) }
    const validJid = j => typeof j === 'string' && /@(s\.whatsapp\.net|lid)$/.test(j)
    if (req.method === 'POST' && (req.url === '/read' || req.url === '/typing' || req.url === '/send')) {
      const b = await body(req)
      if (!sock || state.status !== 'connected') return send(409, { error: 'not connected' })
      if (!validJid(b.jid)) return send(400, { error: 'bad jid' })
      if (req.url === '/read') {
        if (typeof b.id !== 'string') return send(400, { error: 'bad id' })
        await goOnline()
        await sock.readMessages([{ remoteJid: b.jid, id: b.id, fromMe: false }])
        return send(200, { ok: true })
      }
      if (req.url === '/typing') {
        await goOnline()
        await sock.sendPresenceUpdate('composing', b.jid)
        typingSince.set(b.jid, Date.now())
        return send(200, { ok: true })
      }
      if (typeof b.text !== 'string' || !b.text.trim() || b.text.length > 4000) return send(400, { error: 'bad text' })
      if (b.human !== false) {
        const started = typingSince.get(b.jid) ?? Date.now()
        if (!typingSince.has(b.jid)) await sock.sendPresenceUpdate('composing', b.jid)
        const wait = humanDelay(b.text) - (Date.now() - started)
        if (wait > 0) await sleep(wait)
      }
      typingSince.delete(b.jid)
      const sent = await sock.sendMessage(b.jid, { text: b.text })
      await sock.sendPresenceUpdate('paused', b.jid).catch(() => {})
      goOfflineLater()
      return send(200, { id: sent?.key?.id || null })
    }
    return send(404, { error: 'not found' })
  } catch (e) {
    return send(500, { error: e.message })
  }
})

// 127.0.0.1 on the laptop; in Docker BRIDGE_HOST=0.0.0.0 on the private compose network only (port never published)
const HOST = process.env.BRIDGE_HOST || '127.0.0.1'
server.listen(PORT, HOST, () => {
  console.log(`wa-bridge listening on ${HOST}:${PORT} (unofficial WhatsApp linked device)`)
  // restore a saved session automatically
  import('node:fs').then(fs => { if (fs.existsSync(`${SESSION_DIR}/creds.enc`)) connect().catch(e => setState({ status: 'error', lastError: e.message })) })
})
