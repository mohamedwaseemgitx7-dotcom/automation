import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Kb } from '../api'
import { ErrorNote, Header, Pill, type PageProps } from '../App'

export default function Knowledge({ refresh }: PageProps) {
  const [kbs, setKbs] = useState<Kb[]>([])
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const load = useCallback(() => api<Kb[]>('/kb').then(setKbs).catch(e => setError(e.message)), [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!kbs.some(k => k.status === 'processing')) return
    const t = setInterval(() => { load(); refresh() }, 1500)
    return () => clearInterval(t)
  }, [kbs, load, refresh])

  async function upload(f: File) {
    setError(''); setUploading(true)
    const form = new FormData(); form.append('file', f)
    try { await api('/kb/upload', { form }); await load() } catch (e) { setError((e as Error).message) } finally { setUploading(false) }
  }
  const act = async (path: string, method: string) => { try { await api(path, { method }); await load(); refresh() } catch (e) { setError((e as Error).message) } }

  return (
    <>
      <Header title="Knowledge Base" sub="One ZIP with FAQs, price lists and documents. Files are read as data only; nothing inside is executed." />
      <div className="card mb-6 flex flex-col items-center border-dashed py-10 text-center"
        onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) upload(f) }}>
        <div className="font-semibold">{kbs.some(k => k.active) ? 'Replace the knowledge ZIP' : 'Upload your ZIP file'}</div>
        <div className="mt-1 text-sm text-stone-500">PDF · DOCX · TXT · MD · CSV · XLSX · images (vision, if enabled) · audio (Phase 3) — max 100 MB</div>
        <input ref={input} type="file" accept=".zip" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = '' }} />
        <button className="btn mt-4" disabled={uploading} onClick={() => input.current?.click()}>{uploading ? 'Uploading…' : 'Choose ZIP'}</button>
        <ErrorNote error={error} />
      </div>
      {kbs.length === 0 && <div className="text-sm text-stone-500">No knowledge base yet.</div>}
      <div className="space-y-4">
        {kbs.map(kb => (
          <div key={kb.id} className="card">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-semibold">{kb.name} {kb.active && <Pill tone="ok">Active</Pill>}</div>
                <div className="text-xs text-stone-500">{new Date(kb.created_at).toLocaleString()} · {kb.message}</div>
              </div>
              <div className="flex gap-2">
                <Pill tone={kb.status === 'ready' ? 'ok' : kb.status === 'failed' ? 'bad' : 'warn'}>{kb.status}</Pill>
                <button className="btn-ghost" disabled={kb.status === 'processing'} onClick={() => act(`/kb/${kb.id}/reindex`, 'POST')}>Re-index</button>
                <button className="btn-ghost text-bad" disabled={kb.status === 'processing'} onClick={() => { if (confirm(`Delete knowledge base "${kb.name}"?`)) act(`/kb/${kb.id}`, 'DELETE') }}>Delete</button>
              </div>
            </div>
            {kb.status === 'processing' && <div className="mt-3 h-2 overflow-hidden rounded bg-stone-200 dark:bg-stone-800"><div className="h-full bg-accent transition-all" style={{ width: `${kb.progress}%` }} /></div>}
            {kb.files.length > 0 && (
              <table className="mt-4 w-full text-left text-sm">
                <thead className="text-xs uppercase text-stone-500"><tr><th className="py-1">File</th><th>Type</th><th>Status</th><th>Chunks</th><th>Note</th></tr></thead>
                <tbody>{kb.files.map(f => (
                  <tr key={f.path} className="border-t border-stone-100 dark:border-stone-800">
                    <td className="py-1.5 pr-2 font-mono text-xs">{f.path}</td><td>{f.kind}</td>
                    <td><Pill tone={f.status === 'ok' ? 'ok' : f.status === 'failed' ? 'bad' : 'muted'}>{f.status}</Pill></td>
                    <td>{f.chunks}</td><td className="text-xs text-stone-500">{f.error}</td></tr>))}</tbody>
              </table>)}
          </div>
        ))}
      </div>
    </>
  )
}
