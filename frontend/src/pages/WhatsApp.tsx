import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorNote, Header, Pill, type PageProps } from '../App'

type WaStatus = { bridge_running: boolean; status: string; qr: string | null; account: string; error: string; risk_accepted: boolean; risk_text: string }
export type Contact = { id: number; label: string; number: string; automation: boolean; manual_override: boolean; blocked: boolean; conversation_id: number | null; last_message_at: string | null; last_text: string }

const LABEL: Record<string, [string, 'ok' | 'warn' | 'bad' | 'muted']> = {
  connected: ['Connected', 'ok'], qr: ['Scan the QR code', 'warn'], connecting: ['Connecting…', 'warn'],
  reconnecting: ['Reconnecting…', 'warn'], disconnected: ['Not connected', 'muted'], logged_out: ['Logged out', 'bad'], error: ['Error', 'bad'],
}

export default function WhatsApp({ status, refresh }: PageProps) {
  const [wa, setWa] = useState<WaStatus | null>(null)
  const [contacts, setContacts] = useState<Contact[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [label, setLabel] = useState('')
  const [number, setNumber] = useState('')
  const [agree, setAgree] = useState(false)

  const load = useCallback(async () => {
    try { setWa(await api<WaStatus>('/wa/status')); setContacts(await api<Contact[]>('/contacts')) } catch (e) { setError((e as Error).message) }
  }, [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!wa || !['qr', 'connecting', 'reconnecting'].includes(wa.status)) return
    const t = setInterval(load, 2500)
    return () => clearInterval(t)
  }, [wa, load])

  const run = async (fn: () => Promise<unknown>) => { setBusy(true); setError(''); try { await fn(); await load(); refresh() } catch (e) { setError((e as Error).message) } finally { setBusy(false) } }
  const ready = !!status?.ready
  const [txt, tone] = LABEL[wa?.status ?? 'disconnected'] ?? [wa?.status ?? '', 'muted']

  return (
    <>
      <Header title="WhatsApp Connection" sub="Linked-device (QR) connection through an isolated, replaceable adapter." />
      <div className="mb-6 rounded-xl border border-warn/40 bg-warn/10 p-5 text-sm">
        <div className="mb-1 font-semibold text-warn">Unofficial connection: read before linking</div>
        <ul className="list-disc space-y-1 pl-5 text-stone-700 dark:text-stone-300">
          <li>QR / WhatsApp-Web linking is <b>not</b> the official WhatsApp Business API. WhatsApp may log out, restrict or ban the number. No method here can prevent that.</li>
          <li>Link a separate test number first, not the business's main number.</li>
          <li>The agent only replies to the approved contacts below, and only after they message first. No bulk or unsolicited messages.</li>
        </ul>
        {wa && !wa.risk_accepted && (
          <div className="mt-3">
            <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={agree} onChange={e => setAgree(e.target.checked)} /><span>{wa.risk_text}</span></label>
            <button className="btn mt-3" disabled={!agree || busy} onClick={() => run(() => api('/wa/accept-risk', { method: 'POST' }))}>I accept the risk</button>
          </div>)}
        {wa?.risk_accepted && <div className="mt-2 text-xs text-stone-500">Risk accepted by the owner (recorded in Logs).</div>}
      </div>

      <div className="mb-6 grid grid-cols-2 gap-6">
        <div className="card">
          <div className="mb-3 flex items-center justify-between"><span className="font-semibold">Connection</span><Pill tone={tone}>{txt}</Pill></div>
          {wa?.account && <div className="mb-2 text-sm">Linked account: <span className="font-mono">{wa.account}</span></div>}
          {wa?.error && <div className="mb-2 text-xs text-stone-500">{wa.error}</div>}
          {wa?.status === 'qr' && wa.qr && (
            <div className="my-3 text-center">
              <img src={wa.qr} alt="WhatsApp pairing QR code" className="mx-auto rounded-lg bg-white p-2" width={240} height={240} />
              <div className="mt-2 text-xs text-stone-500">WhatsApp → Settings → Linked devices → Link a device. The code refreshes automatically.</div>
            </div>)}
          {!ready && <p className="text-sm text-stone-500">Locked until READY TO START (Dashboard steps 1–3).</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn" disabled={!ready || !wa?.risk_accepted || busy || ['connected', 'qr', 'connecting'].includes(wa?.status ?? '')} onClick={() => run(() => api('/wa/connect', { method: 'POST' }))}>Connect with WhatsApp</button>
            <button className="btn-ghost" disabled={busy || !wa?.bridge_running} onClick={() => run(() => api('/wa/disconnect', { method: 'POST' }))}>Disconnect</button>
            <button className="btn-ghost text-bad" disabled={busy} onClick={() => { if (confirm('Log out the linked device and delete the saved session from this computer?')) run(() => api('/wa/logout', { method: 'POST' })) }}>Log out &amp; delete session</button>
          </div>
        </div>
        <div className="card">
          <div className="mb-3 flex items-center justify-between"><span className="font-semibold">Automatic replies</span>
            <Pill tone={status?.automation ? 'ok' : 'muted'}>{status?.automation ? 'On' : 'Off'}</Pill></div>
          <p className="mb-3 text-sm text-stone-500">When off, messages are stored but nobody gets an AI reply.</p>
          <button className="btn-ghost" disabled={busy} onClick={() => run(() => api('/automation', { method: 'PUT', body: { enabled: !status?.automation } }))}>{status?.automation ? 'Pause all automatic replies' : 'Enable automatic replies'}</button>
        </div>
      </div>

      <div className="card">
        <div className="mb-1 font-semibold">Approved contacts ({contacts.length}/5)</div>
        <p className="mb-3 text-sm text-stone-500">Only these numbers get automatic replies. Everyone else is ignored.</p>
        {contacts.map(c => (
          <div key={c.id} className="flex items-center justify-between border-t border-stone-100 py-2 text-sm dark:border-stone-800">
            <div><span className="font-medium">{c.label}</span> <span className="font-mono text-stone-500">{c.number}</span>
              {c.blocked && <Pill tone="bad">blocked</Pill>} {c.manual_override && <Pill tone="warn">manual</Pill>} {!c.automation && <Pill tone="muted">AI paused</Pill>}</div>
            <div className="flex gap-2">
              <button className="btn-ghost" onClick={() => run(() => api(`/contacts/${c.id}`, { method: 'PATCH', body: { blocked: !c.blocked } }))}>{c.blocked ? 'Unblock' : 'Block'}</button>
              <button className="btn-ghost text-bad" onClick={() => { if (confirm(`Remove ${c.label} and their conversation history?`)) run(() => api(`/contacts/${c.id}`, { method: 'DELETE' })) }}>Remove</button>
            </div>
          </div>))}
        {contacts.length < 5 && (
          <form className="mt-3 flex gap-2" onSubmit={e => { e.preventDefault(); run(async () => { await api('/contacts', { body: { label, number } }); setLabel(''); setNumber('') }) }}>
            <input className="input" placeholder="Name (e.g. Person 1)" value={label} onChange={e => setLabel(e.target.value)} />
            <input className="input" placeholder="Number with country code, e.g. +60 12 345 6789" value={number} onChange={e => setNumber(e.target.value)} />
            <button className="btn" disabled={!label || !number}>Add</button>
          </form>)}
      </div>
      <ErrorNote error={error} />
    </>
  )
}
