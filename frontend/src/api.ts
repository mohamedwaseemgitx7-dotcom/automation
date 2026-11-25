function csrf(): string {
  const m = document.cookie.match(/(?:^|; )agent_csrf=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T = unknown>(path: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const method = opts.method ?? (opts.body || opts.form ? 'POST' : 'GET')
  const headers: Record<string, string> = {}
  if (method !== 'GET') headers['x-csrf-token'] = csrf()
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers['content-type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  const res = await fetch(`/api${path}`, { method, headers, body, credentials: 'same-origin' })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* not json */ }
    throw new ApiError(res.status, msg)
  }
  return res.json() as Promise<T>
}

export type Status = {
  whatsapp: { status: string; account: string }
  knowledge: { active: boolean; name: string | null; files: number; chunks: number }
  llm: { runtime: string | null; chat_model: string; chat_ready: boolean; embed_model: string; embed_ready: boolean; loaded: string[] }
  role_configured: boolean
  automation: boolean
  ready: boolean
  ready_at: string | null
  contacts: number
}

export type Config = {
  bot_name: string; role: string; business_name: string; business_description: string; website: string
  objective: string; allowed_topics: string[]; blocked_topics: string[]; languages: string[]; tone: string
  max_words: number; handoff_message: string; instructions: string
  image_understanding: boolean; voice_understanding: boolean; auto_reply?: boolean
}

export type KbFile = { path: string; kind: string; status: string; chunks: number; error: string }
export type Kb = { id: number; name: string; status: string; active: boolean; progress: number; message: string; created_at: string; files: KbFile[] }
export type Check = { name: string; ok: boolean; detail: string }
export type TestResult = { q: string; expect: string; decision: string; ok: boolean; reply: string; language: string; ms: number; sources: { source: string; score: number }[]; detail: Record<string, unknown> }
export type Readiness = { ready: boolean; at?: string; checks: Check[]; tests: TestResult[] }
export type TestQ = { q: string; expect: 'answer' | 'safe' | 'fallback'; must_include: string[] }
