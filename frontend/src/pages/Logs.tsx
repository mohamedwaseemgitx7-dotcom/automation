import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorNote, Header } from '../App'

type L = { at: string; actor: string; action: string; detail: Record<string, unknown> }

export default function Logs() {
  const [rows, setRows] = useState<L[]>([])
  const [error, setError] = useState('')
  useEffect(() => { api<L[]>('/logs').then(setRows).catch(e => setError(e.message)) }, [])
  return (
    <>
      <Header title="Logs" sub="Owner actions, AI decisions and system events (latest 200)." />
      <ErrorNote error={error} />
      <div className="card">
        {rows.length === 0 ? <div className="text-sm text-stone-500">No events yet.</div> :
          <table className="w-full text-left text-sm"><thead className="text-xs uppercase text-stone-500"><tr><th>Time</th><th>Actor</th><th>Action</th><th>Detail</th></tr></thead>
            <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-stone-100 dark:border-stone-800"><td className="py-1.5 pr-3 text-xs">{new Date(r.at).toLocaleString()}</td><td>{r.actor}</td><td>{r.action}</td><td className="font-mono text-xs text-stone-500">{JSON.stringify(r.detail)}</td></tr>)}</tbody></table>}
      </div>
    </>
  )
}
