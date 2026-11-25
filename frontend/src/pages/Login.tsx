import { useState } from 'react'
import { api } from '../api'
import { ErrorNote } from '../App'

export default function Login({ onDone }: { onDone: () => void }) {
  const [username, setU] = useState('owner')
  const [password, setP] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <div className="grid h-full place-items-center px-4">
      <form className="card w-full max-w-sm" onSubmit={async e => {
        e.preventDefault(); setBusy(true); setError('')
        try { await api('/auth/login', { body: { username, password } }); onDone() } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
      }}>
        <h1 className="text-xl font-bold">Owner login</h1>
        <p className="mb-5 mt-1 text-sm text-stone-500">Local AI WhatsApp Agent</p>
        <label className="label">Username</label>
        <input className="input mb-3" value={username} onChange={e => setU(e.target.value)} autoComplete="username" />
        <label className="label">Password</label>
        <input className="input" type="password" value={password} onChange={e => setP(e.target.value)} autoComplete="current-password" />
        <ErrorNote error={error} />
        <button className="btn mt-5 w-full justify-center" disabled={busy || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}
