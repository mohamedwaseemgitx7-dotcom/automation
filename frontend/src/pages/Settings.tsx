import { Header } from '../App'

export default function Settings({ dark, setDark }: { dark: boolean; setDark: (v: boolean) => void }) {
  return (
    <>
      <Header title="Settings" />
      <div className="card space-y-3 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" checked={dark} onChange={e => setDark(e.target.checked)} /> Dark theme</label>
        <p className="text-stone-500">Owner password: change it with <code>backend\.venv\Scripts\python backend\scripts\set_password.py</code>.</p>
        <p className="text-stone-500">Backups, restore and session deletion are added with Phase 2 and Phase 4.</p>
      </div>
    </>
  )
}
