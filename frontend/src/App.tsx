import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type Status } from './api'
import Dashboard from './pages/Dashboard'
import AgentSetup from './pages/AgentSetup'
import Knowledge from './pages/Knowledge'
import Readiness from './pages/Readiness'
import WhatsApp from './pages/WhatsApp'
import Conversations from './pages/Conversations'
import Models from './pages/Models'
import Logs from './pages/Logs'
import Settings from './pages/Settings'
import Login from './pages/Login'

export type Page = 'dashboard' | 'agent' | 'knowledge' | 'readiness' | 'whatsapp' | 'conversations' | 'models' | 'logs' | 'settings'

const NAV: { id: Page; label: string; icon: string }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: 'M3 12l9-9 9 9M5 10v10h14V10' },
  { id: 'agent', label: 'AI Agent Role', icon: 'M12 3a4 4 0 110 8 4 4 0 010-8zm-7 18a7 7 0 0114 0' },
  { id: 'knowledge', label: 'Knowledge Base', icon: 'M4 4h11l5 5v11H4zM15 4v5h5' },
  { id: 'readiness', label: 'Test & Ready', icon: 'M5 13l4 4L19 7' },
  { id: 'whatsapp', label: 'WhatsApp', icon: 'M4 20l1.5-4A8 8 0 1112 20a8 8 0 01-4-1z' },
  { id: 'conversations', label: 'Conversations', icon: 'M4 5h16v10H8l-4 4z' },
  { id: 'models', label: 'Local Models', icon: 'M4 7h16M4 12h16M4 17h16' },
  { id: 'logs', label: 'Logs', icon: 'M6 4h12v16H6zM9 8h6M9 12h6M9 16h4' },
  { id: 'settings', label: 'Settings', icon: 'M12 9a3 3 0 100 6 3 3 0 000-6zM4 12h2m12 0h2M12 4v2m0 12v2' },
]

export function Icon({ d, className = 'h-4 w-4' }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d={d} />
    </svg>
  )
}

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [page, setPage] = useState<Page>('dashboard')
  const [status, setStatus] = useState<Status | null>(null)
  const [dark, setDark] = useState(() => localStorage.getItem('theme') !== 'light')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  const refresh = useCallback(async () => {
    try {
      setStatus(await api<Status>('/status'))
      setAuthed(true)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setAuthed(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    if (!authed) return
    const t = setInterval(refresh, 8000)
    return () => clearInterval(t)
  }, [authed, refresh])

  if (authed === null) return <div className="grid h-full place-items-center text-sm text-stone-500">Loading…</div>
  if (!authed) return <Login onDone={refresh} />

  const props = { status, refresh, go: setPage }
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white"><Icon d="M8 10h.01M16 10h.01M7 15c3 2 7 2 10 0M5 5h14v14H5z" /></div>
          <div>
            <div className="text-sm font-bold leading-tight">Local AI Agent</div>
            <div className="text-[11px] text-stone-500">runs on this machine</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map(n => (
            <button key={n.id} onClick={() => setPage(n.id)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm ${page === n.id ? 'bg-accent/10 font-semibold text-accent' : 'text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800'}`}>
              <Icon d={n.icon} />{n.label}
            </button>
          ))}
        </nav>
        <div className="space-y-2 border-t border-stone-200 p-4 text-xs dark:border-stone-800">
          <button className="btn-ghost w-full justify-center" onClick={() => setDark(!dark)}>{dark ? 'Light theme' : 'Dark theme'}</button>
          <button className="btn-ghost w-full justify-center" onClick={async () => { await api('/auth/logout', { method: 'POST' }); setAuthed(false) }}>Log out</button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 py-8">
          {page === 'dashboard' && <Dashboard {...props} />}
          {page === 'agent' && <AgentSetup {...props} />}
          {page === 'knowledge' && <Knowledge {...props} />}
          {page === 'readiness' && <Readiness {...props} />}
          {page === 'whatsapp' && <WhatsApp {...props} />}
          {page === 'conversations' && <Conversations />}
          {page === 'models' && <Models />}
          {page === 'logs' && <Logs />}
          {page === 'settings' && <Settings dark={dark} setDark={setDark} />}
        </div>
      </main>
    </div>
  )
}

export type PageProps = { status: Status | null; refresh: () => Promise<void>; go: (p: Page) => void }

export function Header({ title, sub, right }: { title: string; sub?: string; right?: React.ReactNode }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">{sub}</p>}
      </div>
      {right}
    </div>
  )
}

export function Pill({ tone, children }: { tone: 'ok' | 'warn' | 'bad' | 'muted'; children: React.ReactNode }) {
  const c = { ok: 'bg-ok/15 text-ok', warn: 'bg-warn/15 text-warn', bad: 'bg-bad/15 text-bad', muted: 'bg-stone-200 text-stone-600 dark:bg-stone-800 dark:text-stone-300' }[tone]
  return <span className={`badge ${c}`}>{children}</span>
}

export function ErrorNote({ error }: { error: string }) {
  if (!error) return null
  return <div className="mt-3 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</div>
}
