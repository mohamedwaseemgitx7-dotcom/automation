import { Header, Pill, type PageProps } from '../App'

function Step({ n, title, done, text, action, onClick, locked }: { n: number; title: string; done: boolean; text: string; action: string; onClick: () => void; locked?: boolean }) {
  return (
    <div className="card flex items-start gap-4">
      <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold ${done ? 'bg-ok text-white' : 'bg-stone-200 text-stone-600 dark:bg-stone-800 dark:text-stone-300'}`}>{done ? '✓' : n}</div>
      <div className="flex-1">
        <div className="font-semibold">{title}</div>
        <div className="mt-0.5 text-sm text-stone-500 dark:text-stone-400">{text}</div>
      </div>
      <button className="btn-ghost" onClick={onClick} disabled={locked}>{action}</button>
    </div>
  )
}

export default function Dashboard({ status, go }: PageProps) {
  if (!status) return <div className="text-sm text-stone-500">Loading status…</div>
  const s = status
  const llmOk = !!s.llm.runtime && s.llm.chat_ready && s.llm.embed_ready
  return (
    <>
      <Header title="Dashboard" sub="Set up the agent, then connect WhatsApp. Everything runs on this machine." />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="card"><div className="label">WhatsApp</div>
          <Pill tone={s.whatsapp.status === 'connected' ? 'ok' : 'muted'}>{s.whatsapp.status === 'connected' ? 'Connected' : 'Not connected'}</Pill></div>
        <div className="card"><div className="label">Knowledge base</div>
          {s.knowledge.active ? <><Pill tone="ok">Indexed</Pill><div className="mt-2 text-xs text-stone-500">{s.knowledge.files} files · {s.knowledge.chunks} chunks</div></> : <Pill tone="muted">No files uploaded</Pill>}</div>
        <div className="card"><div className="label">Local LLM</div>
          {!s.llm.runtime ? <Pill tone="bad">Not running</Pill> : llmOk ? <Pill tone="ok">Ready</Pill> : <Pill tone="warn">Model missing</Pill>}
          <div className="mt-2 truncate text-xs text-stone-500">{s.llm.chat_model} · {s.llm.embed_model}</div></div>
        <div className="card"><div className="label">Automation</div>
          <Pill tone={s.automation ? 'ok' : 'muted'}>{s.automation ? 'Enabled' : 'Disabled'}</Pill></div>
      </div>
      {s.ready && <div className="mb-6 rounded-xl border border-ok/40 bg-ok/10 p-5 text-center"><div className="text-lg font-bold text-ok">READY TO START</div><div className="text-sm text-stone-600 dark:text-stone-300">All readiness checks passed. You can connect WhatsApp.</div></div>}
      <div className="space-y-3">
        <Step n={1} title="Create the AI agent role" done={s.role_configured} text="Bot name, business, what it may and may not answer, languages, tone." action="Open" onClick={() => go('agent')} />
        <Step n={2} title="Upload the business knowledge ZIP" done={s.knowledge.active} text="FAQs, price lists, documents. Processed locally into a searchable knowledge base." action="Open" onClick={() => go('knowledge')} />
        <Step n={3} title="Test and verify readiness" done={s.ready} text="Runs real questions through the local model, checks fallbacks and that no external AI is used." action="Open" onClick={() => go('readiness')} />
        <Step n={4} title="Connect WhatsApp (QR)" done={s.whatsapp.status === 'connected'} text={s.ready ? 'Unofficial linked-device connection. Read the risk notice first.' : 'Locked until READY TO START.'} action="Open" onClick={() => go('whatsapp')} locked={!s.ready} />
      </div>
    </>
  )
}
