import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorNote, Header, Pill } from '../App'
import type { Contact } from './WhatsApp'

type Msg = { id: number; direction: string; type: string; text: string | null; decision: string | null; language: string | null; sources: { source: string; score?: number }[]; status: string; latency_ms: number | null; at: string }

export default function Conversations() {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [sel, setSel] = useState<Contact | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [reply, setReply] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const cs = await api<Contact[]>('/contacts'); setContacts(cs)
      const cur = sel ? cs.find(c => c.id === sel.id) ?? null : null
      setSel(cur)
      if (cur?.conversation_id) setMsgs(await api<Msg[]>(`/conversations/${cur.conversation_id}/messages`)); else setMsgs([])
    } catch (e) { setError((e as Error).message) }
  }, [sel])
  useEffect(() => { load() }, [load])
  useEffect(() => { const t = setInterval(load, 4000); return () => clearInterval(t) }, [load])

  const patch = async (body: object) => { if (!sel) return; try { await api(`/contacts/${sel.id}`, { method: 'PATCH', body }); load() } catch (e) { setError((e as Error).message) } }
  return (
    <>
      <Header title="Conversations" sub="One separate history per approved contact. A manual reply switches that chat to manual mode." />
      <ErrorNote error={error} />
      {contacts.length === 0 ? <div className="card text-sm text-stone-500">No approved contacts yet. Add them on the WhatsApp page.</div> :
        <div className="grid grid-cols-[220px_1fr] gap-6">
          <div className="space-y-2">{contacts.map(c => (
            <button key={c.id} onClick={() => setSel(c)} className={`card w-full p-3 text-left ${sel?.id === c.id ? 'ring-2 ring-accent' : ''}`}>
              <div className="text-sm font-semibold">{c.label}</div>
              <div className="truncate text-xs text-stone-500">{c.last_text || 'No messages yet'}</div>
            </button>))}</div>
          {!sel ? <div className="card text-sm text-stone-500">Choose a contact.</div> :
            <div className="card flex flex-col">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="font-semibold">{sel.label}</span><span className="font-mono text-xs text-stone-500">{sel.number}</span>
                {sel.manual_override ? <Pill tone="warn">Manual mode – AI silent</Pill> : sel.automation ? <Pill tone="ok">AI active</Pill> : <Pill tone="muted">AI paused</Pill>}
                <div className="ml-auto flex gap-2">
                  {sel.manual_override && <button className="btn-ghost" onClick={() => patch({ manual_override: false })}>Resume AI</button>}
                  <button className="btn-ghost" onClick={() => patch({ automation: !sel.automation })}>{sel.automation ? 'Pause AI for this contact' : 'Resume AI for this contact'}</button>
                </div>
              </div>
              <div className="mb-3 max-h-[28rem] flex-1 space-y-3 overflow-y-auto text-sm">
                {msgs.length === 0 && <div className="text-stone-500">No messages yet.</div>}
                {msgs.map(m => (
                  <div key={m.id} className={m.direction === 'out' ? 'text-right' : ''}>
                    <div className={`inline-block max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-2 text-left ${m.direction === 'out' ? 'bg-accent text-white' : 'bg-stone-100 dark:bg-stone-800'}`}>{m.text ?? `[${m.type}]`}</div>
                    <div className="mt-0.5 text-[11px] text-stone-500">{new Date(m.at).toLocaleTimeString()} · {m.type}{m.decision ? ` · ${m.decision}` : ''}{m.status === 'failed' ? ' · SEND FAILED' : ''}{m.latency_ms ? ` · ${m.latency_ms} ms` : ''}{m.sources?.length ? ` · ${m.sources.map(s => s.source).join(', ')}` : ''}</div>
                  </div>))}
              </div>
              <form className="flex gap-2" onSubmit={async e => { e.preventDefault(); try { await api(`/conversations/${sel.conversation_id}/reply`, { body: { text: reply } }); setReply(''); load() } catch (err) { setError((err as Error).message) } }}>
                <input className="input" value={reply} onChange={e => setReply(e.target.value)} placeholder="Reply manually (AI pauses in this chat)" disabled={!sel.conversation_id} />
                <button className="btn" disabled={!reply.trim() || !sel.conversation_id}>Send</button>
              </form>
            </div>}
        </div>}
    </>
  )
}
