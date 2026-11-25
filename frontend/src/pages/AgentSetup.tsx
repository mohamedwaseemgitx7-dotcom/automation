import { useEffect, useState } from 'react'
import { api, type Config } from '../api'
import { ErrorNote, Header, type PageProps } from '../App'

const LANGS = ['English', 'Malay', 'Tamil', 'Tanglish']
const list = (s: string) => s.split(/\n|,/).map(x => x.trim()).filter(Boolean)

export default function AgentSetup({ refresh }: PageProps) {
  const [c, setC] = useState<Config | null>(null)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')
  const [allowed, setAllowed] = useState('')
  const [blocked, setBlocked] = useState('')

  useEffect(() => {
    api<Config>('/config').then(cfg => { setC(cfg); setAllowed(cfg.allowed_topics.join('\n')); setBlocked(cfg.blocked_topics.join('\n')) })
      .catch(e => setError(e.message))
  }, [])
  if (!c) return <div className="text-sm text-stone-500">{error || 'Loading…'}</div>
  const set = <K extends keyof Config>(k: K, v: Config[K]) => setC({ ...c, [k]: v })

  async function save() {
    setError(''); setMsg('')
    try {
      await api('/config', { method: 'PUT', body: { ...c, allowed_topics: list(allowed), blocked_topics: list(blocked) } })
      setMsg('Saved. Run the readiness test again after changes.'); refresh()
    } catch (e) { setError((e as Error).message) }
  }

  const text = (k: keyof Config, label: string, ph = '') => (
    <div><label className="label">{label}</label><input className="input" value={String(c[k] ?? '')} placeholder={ph} onChange={e => set(k, e.target.value as never)} /></div>
  )
  return (
    <>
      <Header title="AI Agent Role" sub="Defines what the agent is and what it may answer. Business facts come only from the knowledge ZIP."
        right={<button className="btn" onClick={save}>Save role</button>} />
      <div className="card grid grid-cols-2 gap-4">
        {text('bot_name', 'Bot name', 'e.g. Sam')}
        {text('role', 'Bot role', 'e.g. Sales Assistant')}
        {text('business_name', 'Business name', 'e.g. Smartech Synergys')}
        {text('website', 'Website (reference only, not scraped)', 'https://')}
        <div className="col-span-2"><label className="label">Business description</label>
          <textarea className="input h-20" value={c.business_description} onChange={e => set('business_description', e.target.value)} /></div>
        <div className="col-span-2"><label className="label">Main objective</label>
          <textarea className="input h-16" value={c.objective} onChange={e => set('objective', e.target.value)} placeholder="e.g. Answer service and product questions and pass sales leads to the owner." /></div>
        <div><label className="label">Allowed question topics (one per line)</label>
          <textarea className="input h-28" value={allowed} onChange={e => setAllowed(e.target.value)} placeholder={'services\nproducts\nopening hours\nservice area'} /></div>
        <div><label className="label">Refuse these topics (one per line)</label>
          <textarea className="input h-28" value={blocked} onChange={e => setBlocked(e.target.value)} placeholder={'politics\njokes\npersonal questions\ncompetitors'} /></div>
        <div><label className="label">Languages</label>
          <div className="flex flex-wrap gap-2">{LANGS.map(l => (
            <label key={l} className="btn-ghost cursor-pointer"><input type="checkbox" checked={c.languages.includes(l)}
              onChange={e => set('languages', e.target.checked ? [...c.languages, l] : c.languages.filter(x => x !== l))} />{l}</label>))}</div></div>
        <div className="grid grid-cols-2 gap-3">
          {text('tone', 'Tone')}
          <div><label className="label">Max words per reply</label><input className="input" type="number" min={20} max={300} value={c.max_words} onChange={e => set('max_words', Number(e.target.value))} /></div>
        </div>
        <div className="col-span-2"><label className="label">Fallback / human handoff message</label>
          <input className="input" value={c.handoff_message} onChange={e => set('handoff_message', e.target.value)} /></div>
        <div className="col-span-2"><label className="label">Extra instructions</label>
          <textarea className="input h-24" value={c.instructions} onChange={e => set('instructions', e.target.value)} placeholder="e.g. Always ask for the device model when a customer reports a fault." /></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={c.image_understanding} onChange={e => set('image_understanding', e.target.checked)} /> Image understanding (local vision model)</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={c.voice_understanding} onChange={e => set('voice_understanding', e.target.checked)} /> Voice notes (Phase 3)</label>
      </div>
      {msg && <div className="mt-3 text-sm text-ok">{msg}</div>}
      <ErrorNote error={error} />
    </>
  )
}
