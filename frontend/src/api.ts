// API 封装与类型定义
export interface CheckListItem {
  id: string
  title: string
  language: string
  word_count: number
  status: string
  created_at: string
}

export interface SourceInfo {
  doc_id: number
  title: string
  dup_units: number
  hits?: number
  rate: number
}

export interface FragSource {
  doc_id: number
  title: string
  src_text: string
  sim: number
}

export interface Fragment {
  start: number
  end: number
  text: string
  dup_units: number
  rate: number
  best_source: FragSource
  all_sources: FragSource[]
}

export interface SentResult {
  start: number
  end: number
  text: string
  units: number
  norm?: string
  kind?: string
  matched: boolean
  best?: FragSource
  all_sources?: FragSource[]
  web?: WebHit
}

export interface WebHit {
  url: string
  title: string
  sim: number
}

export interface WebCheck {
  status: 'ok' | 'partial' | 'error'
  provider: string
  checked: number
  candidates: number
  failed: number
  web_dup_rate: number
  web_dup_units: number
  hits: (WebHit & { start: number; end: number; text: string; units: number; snippet: string })[]
  sources: { url: string; title: string; units: number; hits: number; rate: number }[]
  note: string
}

export interface Plagiarism {
  total_rate: number
  quote_rate?: number
  dup_units: number
  total_units: number
  sentence_count: number
  matched_sentences: number
  fragments: Fragment[]
  sources: SourceInfo[]
  sent_results: SentResult[]
  web?: WebCheck
}

export interface AigcEngine {
  key: string
  name: string
  region: string
  status: 'ok' | 'not_configured' | 'error' | 'manual' | 'experimental'
  rate: number | null
  note: string
  sentence_scores: AigcSentence[]
}

export interface AigcSentence {
  start: number
  end: number
  text: string
  score: number
  level: 'high' | 'mid' | 'low'
}

export interface AigcLocal extends AigcEngine {
  paragraphs: { index: number; start: number; end: number; rate: number; high_count: number; count: number }[]
  features: Record<string, number>
}
export interface Aigc {
  engines: AigcEngine[]
  local: AigcLocal | null
}

export interface Report {
  plagiarism: Plagiarism | null
  aigc: Aigc | null
  options: { mode?: string; strip_references?: boolean }
}

export interface CheckDetail {
  id: string
  title: string
  language: string
  word_count: number
  status: 'queued' | 'running' | 'done' | 'error'
  report?: Report
  error?: string
  created_at: string
  finished_at?: string
}

export interface LibraryDoc {
  id: number
  title: string
  word_count: number
  is_builtin: number
  created_at: string
}

export interface EngineInfo {
  key: string
  name: string
  region: string
  desc: string
  type: 'api' | 'manual' | 'search' | 'model'
  configured: boolean
  enabled: boolean
  experimental?: boolean
}

export interface CrawlSource {
  key: string
  name: string
  region: string
  langs: string
  desc: string
  default_query: string
  max_target: number
}

export interface CrawlJob {
  id: string
  source: string
  query: string
  target: number
  fetched: number
  added: number
  status: 'running' | 'stop_requested' | 'stopped' | 'done' | 'error'
  message: string | null
  created_at: string
  updated_at: string
}

export interface Stats {
  corpus: { documents: number; builtin_documents: number; sentences: number; units: number }
  total_checks: number
  engines: number
}

// ---------- 管理员令牌（仅存 sessionStorage，关闭标签页即清除） ----------
const TOKEN_KEY = 'paperlens_admin_token'

export function getAdminToken(): string {
  return sessionStorage.getItem(TOKEN_KEY) ?? ''
}
export function setAdminToken(t: string): void {
  sessionStorage.setItem(TOKEN_KEY, t.trim())
}
export function clearAdminToken(): void {
  sessionStorage.removeItem(TOKEN_KEY)
}

// 全部 API 请求统一走 apiFetch：自动附带 X-Admin-Token；401 时清除令牌并广播
export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  const t = getAdminToken()
  if (t) headers.set('X-Admin-Token', t)
  const res = await fetch(input, { ...init, headers })
  if (res.status === 401) {
    clearAdminToken()
    window.dispatchEvent(new CustomEvent('paperlens:unauthorized'))
  }
  return res
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`
    try {
      const j = await res.json()
      if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* ignore */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export const api = {
  stats: () => apiFetch('/api/stats').then(handle<Stats>),
  createCheckByFile: (file: File, opts: { title: string; mode: string; stripReferences: boolean; webCheck?: boolean; webCheckCount?: number }) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('title', opts.title)
    fd.append('mode', opts.mode)
    fd.append('strip_references', String(opts.stripReferences))
    fd.append('web_check', String(opts.webCheck ?? false))
    fd.append('web_check_count', String(opts.webCheckCount ?? 10))
    return apiFetch('/api/checks', { method: 'POST', body: fd }).then(handle<{ check_id: string }>)
  },
  createCheckByText: (text: string, opts: { title: string; mode: string; stripReferences: boolean; webCheck?: boolean; webCheckCount?: number }) => {
    const fd = new FormData()
    fd.append('text', text)
    fd.append('title', opts.title)
    fd.append('mode', opts.mode)
    fd.append('strip_references', String(opts.stripReferences))
    fd.append('web_check', String(opts.webCheck ?? false))
    fd.append('web_check_count', String(opts.webCheckCount ?? 10))
    return apiFetch('/api/checks', { method: 'POST', body: fd }).then(handle<{ check_id: string }>)
  },
  getCheck: (id: string) => apiFetch(`/api/checks/${id}`).then(handle<CheckDetail>),
  listChecks: () => apiFetch('/api/checks').then(handle<CheckListItem[]>),
  deleteCheck: (id: string) => apiFetch(`/api/checks/${id}`, { method: 'DELETE' }).then(handle<{ ok: boolean }>),
  listDocs: () => apiFetch('/api/library/documents').then(handle<LibraryDoc[]>),
  addDocByFile: (file: File, title: string) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('title', title)
    return apiFetch('/api/library/documents', { method: 'POST', body: fd }).then(handle<{ id: number }>)
  },
  addDocByText: (text: string, title: string) => {
    const fd = new FormData()
    fd.append('text', text)
    fd.append('title', title)
    return apiFetch('/api/library/documents', { method: 'POST', body: fd }).then(handle<{ id: number }>)
  },
  deleteDoc: (id: number) => apiFetch(`/api/library/documents/${id}`, { method: 'DELETE' }).then(handle<{ ok: boolean }>),
  listEngines: () => apiFetch('/api/engines').then(handle<EngineInfo[]>),
  configEngine: (key: string, apiKey: string, enabled: boolean) => {
    const fd = new FormData()
    fd.append('api_key', apiKey)
    fd.append('enabled', String(enabled))
    return apiFetch(`/api/engines/${key}/config`, { method: 'POST', body: fd }).then(handle<{ ok: boolean }>)
  },
  crawlSources: () => apiFetch('/api/crawl/sources').then(handle<CrawlSource[]>),
  crawlJobs: () => apiFetch('/api/crawl/jobs').then(handle<CrawlJob[]>),
  startCrawl: (source: string, query: string, target: number) =>
    apiFetch('/api/crawl/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, query, target }),
    }).then(handle<{ job_id: string }>),
  stopCrawl: (id: string) =>
    apiFetch(`/api/crawl/jobs/${id}/stop`, { method: 'POST' }).then(handle<{ ok: boolean }>),
}

export function rateColor(rate: number): string {
  if (rate < 10) return '#16a34a'
  if (rate < 25) return '#d97706'
  return '#dc2626'
}

export function rateLabel(rate: number): string {
  if (rate < 10) return '通过'
  if (rate < 25) return '关注'
  return '偏高'
}

export function aigcColor(rate: number): string {
  if (rate < 30) return '#16a34a'
  if (rate < 60) return '#d97706'
  return '#dc2626'
}
