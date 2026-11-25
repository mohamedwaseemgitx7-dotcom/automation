import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorNote, Header, Pill } from '../App'

type M = { runtime: string | null; installed: { name: string; size_gb: number; family: string; quant: string }[]; loaded: { name: string; vram_gb: number }[]; config: Record<string, string> }

export default function Models() {
  const [m, setM] = useState<M | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { api<M>('/models').then(setM).catch(e => setError(e.message)) }, [])
  if (!m) return <><Header title="Local Models" /><ErrorNote error={error} /></>
  const has = (n: string) => m.installed.some(i => i.name === n || i.name === `${n}:latest`)
  return (
    <>
      <Header title="Local Models" sub="Ollama on 127.0.0.1 only. No hosted AI service is ever called." />
      <div className="card mb-6 text-sm">Runtime: {m.runtime ? <Pill tone="ok">Ollama {m.runtime}</Pill> : <Pill tone="bad">Not running</Pill>}
        <span className="ml-3 text-stone-500">In GPU memory now: {m.loaded.length ? m.loaded.map(l => `${l.name} (${l.vram_gb} GB)`).join(', ') : 'none'}</span></div>
      <div className="card mb-6">
        <div className="mb-2 font-semibold">Configured</div>
        <ul className="space-y-1 text-sm">{Object.entries(m.config).map(([k, v]) => (
          <li key={k} className="flex gap-3"><span className="w-16 text-stone-500">{k}</span><span className="font-mono">{v}</span>{has(v) ? <Pill tone="ok">installed</Pill> : <Pill tone="warn">not downloaded</Pill>}</li>))}</ul>
      </div>
      <div className="card"><div className="mb-2 font-semibold">Installed</div>
        {m.installed.length === 0 ? <div className="text-sm text-stone-500">No models installed.</div> :
          <table className="w-full text-left text-sm"><thead className="text-xs uppercase text-stone-500"><tr><th>Name</th><th>Family</th><th>Quant</th><th>Size</th></tr></thead>
            <tbody>{m.installed.map(i => <tr key={i.name} className="border-t border-stone-100 dark:border-stone-800"><td className="py-1.5 font-mono">{i.name}</td><td>{i.family}</td><td>{i.quant}</td><td>{i.size_gb} GB</td></tr>)}</tbody></table>}
      </div>
    </>
  )
}
