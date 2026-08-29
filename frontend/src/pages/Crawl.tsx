import { useEffect, useState } from 'react'
import {
  Globe, RefreshCw, Square, Database, BookOpen, ExternalLink, CheckCircle2, AlertTriangle,
} from 'lucide-react'
import { api, CrawlJob, CrawlSource } from '../api'

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  running: { label: '采集中', cls: 'bg-indigo-50 text-indigo-600' },
  stop_requested: { label: '停止中', cls: 'bg-amber-50 text-amber-600' },
  stopped: { label: '已停止', cls: 'bg-slate-100 text-slate-500' },
  done: { label: '已完成', cls: 'bg-emerald-50 text-emerald-600' },
  error: { label: '出错', cls: 'bg-red-50 text-red-600' },
}

export default function Crawl() {
  const [sources, setSources] = useState<CrawlSource[]>([])
  const [jobs, setJobs] = useState<CrawlJob[]>([])
  const [queries, setQueries] = useState<Record<string, string>>({})
  const [targets, setTargets] = useState<Record<string, number>>({})
  const [msg, setMsg] = useState('')

  const load = () => {
    api.crawlSources().then(setSources).catch(() => {})
    api.crawlJobs().then(setJobs).catch(() => {})
  }
  useEffect(() => {
    load()
    const t = setInterval(() => {
      api.crawlJobs().then(setJobs).catch(() => {})
    }, 2500)
    return () => clearInterval(t)
  }, [])

  const start = async (s: CrawlSource) => {
    setMsg('')
    try {
      await api.startCrawl(s.key, queries[s.key] ?? '', targets[s.key] ?? 200)
      setMsg(`已启动采集任务：${s.name}`)
      load()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '启动失败')
    }
  }

  const stop = async (id: string) => {
    await api.stopCrawl(id)
    load()
  }

  const activeJobs = jobs.filter(j => j.status === 'running' || j.status === 'stop_requested')

  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-800">语料采集（OA 开放论文）</h1>
      <p className="mt-1.5 text-sm text-slate-500 leading-relaxed">
        从四个官方开放学术数据源批量抓取 OA 论文的标题与摘要，入库后立即参与查重比对。
        全部为官方 API、礼貌抓取、按标题去重，文献来源与链接会保留在比对命中记录中。
      </p>

      <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800 leading-relaxed">
        <b>规模说明：</b>
        全球 OA 论文总量达数千万篇（OpenAlex 索引 2.5 亿+ 篇文献元数据），本机入库为增量积累模式——
        可反复采集不同关键词/数据源持续扩库，索引在万篇级规模内依然保持秒级检索；
        未入库的公开网页则在检测时通过「联网全网核查」实时覆盖。
      </div>

      {msg && (
        <div className="mt-4 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm px-4 py-2.5">
          {msg}
        </div>
      )}

      {/* 数据源卡片 */}
      <div className="mt-6 grid md:grid-cols-2 gap-4">
        {sources.map(s => (
          <div key={s.key} className="bg-white rounded-2xl border border-slate-200 p-5">
            <div className="flex items-center gap-2">
              <Globe size={16} className="text-indigo-500" />
              <h3 className="font-semibold text-slate-800">{s.name}</h3>
              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-500 text-xs">{s.region}</span>
              <span className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-500 text-xs">{s.langs}</span>
            </div>
            <p className="mt-2 text-xs text-slate-500 leading-relaxed min-h-[32px]">{s.desc}</p>
            <div className="mt-3 flex gap-2">
              <input
                value={queries[s.key] ?? ''}
                onChange={e => setQueries({ ...queries, [s.key]: e.target.value })}
                placeholder={`检索词（留空 = ${s.default_query || '全部'}）`}
                className="flex-1 min-w-0 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
              />
              <select
                value={targets[s.key] ?? 200}
                onChange={e => setTargets({ ...targets, [s.key]: Number(e.target.value) })}
                className="border border-slate-200 rounded-lg px-2 py-2 text-sm bg-white"
              >
                {[100, 200, 500, 1000, 2000].map(n => (
                  <option key={n} value={n}>{n} 篇</option>
                ))}
              </select>
              <button
                onClick={() => start(s)}
                className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-700 whitespace-nowrap"
              >
                开始采集
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* 进行中的任务 */}
      {activeJobs.length > 0 && (
        <section className="mt-8 bg-white rounded-2xl border border-slate-200 p-6">
          <h3 className="font-semibold text-slate-700 flex items-center gap-2 text-sm">
            <RefreshCw size={15} className="animate-spin text-indigo-500" /> 进行中的任务
          </h3>
          <div className="mt-4 space-y-4">
            {activeJobs.map(j => {
              const pct = Math.min(100, Math.round((j.fetched / Math.max(1, j.target)) * 100))
              return (
                <div key={j.id}>
                  <div className="flex items-center gap-3 text-sm">
                    <span className="font-medium text-slate-700 w-44 truncate">{sourceName(sources, j.source)}</span>
                    <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full bg-indigo-500 transition-all" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-xs text-slate-500 w-28 text-right">
                      {j.fetched}/{j.target} · 入库 {j.added}
                    </span>
                    <button
                      onClick={() => stop(j.id)}
                      className="px-3 py-1 rounded-lg border border-slate-200 text-slate-500 text-xs hover:bg-slate-50"
                    >
                      <Square size={11} className="inline mr-1" /> 停止
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 历史任务 */}
      <section className="mt-6 bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-100 flex items-center gap-2 text-sm font-medium text-slate-700">
          <Database size={15} className="text-indigo-500" /> 采集任务记录
          <button onClick={load} className="ml-auto text-xs text-indigo-500 hover:underline">刷新</button>
        </div>
        {jobs.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-400">
            暂无任务。选择上方数据源开始采集，抓到的论文会出现在「文档库」中。
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-slate-500 text-left">
                <th className="px-5 py-3 font-medium">数据源</th>
                <th className="px-5 py-3 font-medium">检索词</th>
                <th className="px-5 py-3 font-medium">状态</th>
                <th className="px-5 py-3 font-medium">抓取/入库</th>
                <th className="px-5 py-3 font-medium">说明</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {jobs.map(j => {
                const badge = STATUS_BADGE[j.status] ?? STATUS_BADGE.stopped
                return (
                  <tr key={j.id}>
                    <td className="px-5 py-3 text-slate-700">{sourceName(sources, j.source)}</td>
                    <td className="px-5 py-3 text-slate-500 max-w-[160px] truncate">{j.query || '—'}</td>
                    <td className="px-5 py-3">
                      <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${badge.cls}`}>
                        {j.status === 'running' && <RefreshCw size={10} className="inline mr-1 animate-spin" />}
                        {j.status === 'done' && <CheckCircle2 size={10} className="inline mr-1" />}
                        {j.status === 'error' && <AlertTriangle size={10} className="inline mr-1" />}
                        {badge.label}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-600">{j.fetched} / {j.added}</td>
                    <td className="px-5 py-3 text-xs text-slate-400 max-w-[260px] truncate" title={j.message ?? ''}>
                      {j.message || '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>

      <p className="mt-4 text-xs text-slate-400 flex items-center gap-1.5">
        <BookOpen size={13} />
        比对命中 OA 文献时会展示论文标题与来源链接；
        请遵守各数据源的使用条款，采集仅用于学术比对用途。
        <ExternalLink size={12} />
      </p>
    </div>
  )
}

function sourceName(sources: CrawlSource[], key: string): string {
  return sources.find(s => s.key === key)?.name ?? key
}
