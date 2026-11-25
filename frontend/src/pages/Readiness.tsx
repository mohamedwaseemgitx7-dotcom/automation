import { useEffect, useState } from 'react'
import { api, type Readiness as R, type TestQ } from '../api'
import { ErrorNote, Header, Pill, type PageProps } from '../App'

type Chat = { q: string; reply: string; decision: string; sources: { source: string; score: number }[]; ms: number; lang: string }

export default function Readiness({ refresh }: PageProps) {
  const [tests, setTests] = useState<TestQ[]>([])
  const [report, setReport] = useState<R | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [chat, setChat] = useState<Chat[]>([])
  const [asking, setAsking] = useState(false)

  useEffect(() => {
    api<TestQ[]>('/readiness/questions').then(setTests).catch(e => setError(e.message))
    api<R | null>('/readiness/latest').then(setReport).catch(() => {})
  }, [])

  async function saveTests(t: TestQ[]) { setTests(t); await api('/readiness/questions', { method: 'PUT', body: t }) }
  async function run() {
    setRunning(true); setError('')
    try { setReport(await api<R>('/readiness/run', { method: 'POST' })); refresh() } catch (e) { setError((e as Error).message) } finally { setRunning(false) }
  }
  async function ask() {
    if (!q.trim()) return
    setAsking(true); setError('')
    try {
      const r = await api<{ reply: string; decision: string; sources: Chat['sources']; latency_ms: number; language: string }>('/agent/ask', { body: { question: q, history: chat.slice(-4).map(c => c.q) } })
      setChat([...chat, { q, reply: r.reply, decision: r.decision, sources: r.sources, ms: r.latency_ms, lang: r.language }]); setQ('')
    } catch (e) { setError((e as Error).message) } finally { setAsking(false) }
  }

  return (
    <>
      <Header title="Test & Ready" sub="Real questions through the local model. READY TO START appears only when every check passes."
        right={<button className="btn" disabled={running} onClick={run}>{running ? 'Running tests… (can take minutes)' : 'Run readiness check'}</button>} />
      <ErrorNote error={error} />
      {report && (
        <div className="card mb-6">
          <div className="mb-3 flex items-center justify-between"><div className="font-semibold">Last result</div>
            {report.ready ? <Pill tone="ok">READY TO START</Pill> : <Pill tone="bad">Not ready</Pill>}</div>
          <ul className="space-y-1 text-sm">{report.checks.map(c => (
            <li key={c.name} className="flex gap-2"><span className={c.ok ? 'text-ok' : 'text-bad'}>{c.ok ? '✓' : '✗'}</span><span className="font-medium">{c.name}</span><span className="text-stone-500">{c.detail}</span></li>))}</ul>
          {report.tests.length > 0 && <table className="mt-4 w-full text-left text-sm">
            <thead className="text-xs uppercase text-stone-500"><tr><th>Question</th><th>Expect</th><th>Got</th><th>Reply</th><th>ms</th></tr></thead>
            <tbody>{report.tests.map((t, i) => (
              <tr key={i} className="border-t border-stone-100 align-top dark:border-stone-800">
                <td className="py-1.5 pr-2">{t.q}</td><td>{t.expect}</td><td><Pill tone={t.ok ? 'ok' : 'bad'}>{t.decision}</Pill></td>
                <td className="pr-2 text-xs text-stone-600 dark:text-stone-300">{t.reply}</td><td className="text-xs">{t.ms}</td></tr>))}</tbody></table>}
        </div>)}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <div className="mb-2 font-semibold">Test questions</div>
          <p className="mb-3 text-xs text-stone-500">Add real customer questions with the answer type you expect. Off-topic checks are added automatically.</p>
          {tests.map((t, i) => (
            <div key={i} className="mb-2 flex gap-2">
              <input className="input" value={t.q} onChange={e => { const n = [...tests]; n[i] = { ...t, q: e.target.value }; setTests(n) }} onBlur={() => saveTests(tests)} />
              <select className="input w-32" value={t.expect} onChange={e => { const n = [...tests]; n[i] = { ...t, expect: e.target.value as TestQ['expect'] }; saveTests(n) }}>
                <option value="answer">answer</option><option value="safe">safe</option><option value="fallback">fallback</option></select>
              <button className="btn-ghost" onClick={() => saveTests(tests.filter((_, j) => j !== i))}>✕</button>
            </div>))}
          <button className="btn-ghost mt-1" onClick={() => setTests([...tests, { q: '', expect: 'answer', must_include: [] }])}>+ Add question</button>
        </div>
        <div className="card flex flex-col">
          <div className="mb-2 font-semibold">Try the agent</div>
          <div className="mb-3 max-h-96 flex-1 space-y-3 overflow-y-auto text-sm">
            {chat.length === 0 && <div className="text-stone-500">Ask a question as a customer would.</div>}
            {chat.map((c, i) => (
              <div key={i}>
                <div className="ml-auto w-fit max-w-[85%] rounded-lg bg-accent px-3 py-2 text-white">{c.q}</div>
                <div className="mt-1 w-fit max-w-[85%] whitespace-pre-wrap rounded-lg bg-stone-100 px-3 py-2 dark:bg-stone-800">{c.reply}</div>
                <div className="mt-1 text-[11px] text-stone-500">{c.decision} · {c.lang} · {c.ms} ms {c.sources.length > 0 && `· ${c.sources.map(s => `${s.source} (${s.score})`).join(', ')}`}</div>
              </div>))}
          </div>
          <form className="flex gap-2" onSubmit={e => { e.preventDefault(); ask() }}>
            <input className="input" value={q} onChange={e => setQ(e.target.value)} placeholder="e.g. How much is SSD upgrade?" />
            <button className="btn" disabled={asking}>{asking ? '…' : 'Ask'}</button>
          </form>
        </div>
      </div>
    </>
  )
}
