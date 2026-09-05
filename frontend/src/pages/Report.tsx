import { useCallback, useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Download, ArrowLeft, Loader2, FileSearch, Bot, AlertTriangle,
  Copy, FileText, Gauge, Globe, ExternalLink,
} from 'lucide-react'
import {
  api, apiFetch, CheckDetail, rateColor, rateLabel, aigcColor, FragSource, AigcSentence,
} from '../api'
import RingGauge from '../components/RingGauge'
import Radar from '../components/Radar'

type Tab = 'overview' | 'fulltext' | 'fragments' | 'web' | 'aigc'

const tabs: { key: Tab; label: string }[] = [
  { key: 'overview', label: '检测总览' },
  { key: 'fulltext', label: '全文标红' },
  { key: 'fragments', label: '相似片段' },
  { key: 'web', label: '联网核查' },
  { key: 'aigc', label: 'AIGC 明细' },
]

export default function Report() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<CheckDetail | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<Tab>('overview')
  const [progress, setProgress] = useState<{ stage?: string; pct: number } | null>(null)

  const load = useCallback(() => {
    if (!id) return
    api.getCheck(id).then(setData).catch(e => {
      setError(e instanceof Error ? e.message : '加载失败')
    })
  }, [id])

  // 导出走 apiFetch（令牌模式下才能通过网关），成功后以 blob 下载
  const exportReport = async () => {
    if (!id) return
    const res = await apiFetch(`/api/checks/${id}/export`)
    if (!res.ok) return
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `report_${id}.html`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  useEffect(() => {
    load()
  }, [load])

  // 检测中：SSE 订阅进度（断连自动回退轮询）
  useEffect(() => {
    if (!data || data.status === 'done' || data.status === 'error') return
    let fallback: number | undefined
    const es = new EventSource(`/api/checks/${data.id}/events`)
    es.onmessage = ev => {
      try {
        const p = JSON.parse(ev.data)
        setProgress({ stage: p.stage, pct: p.pct ?? 0 })
        if (p.status === 'error') { es.close(); load() }
      } catch { /* 忽略格式异常 */ }
    }
    es.addEventListener('end', () => { es.close(); load() })
    es.onerror = () => {
      es.close()
      fallback = window.setTimeout(load, 1200)
    }
    return () => { es.close(); if (fallback) clearTimeout(fallback) }
  }, [data, load])

  if (error) {
    return <Center><AlertTriangle className="text-amber-400" size={36} />
      <p className="mt-3 text-slate-600">{error}</p>
      <Link to="/submit" className="mt-4 text-indigo-600 text-sm hover:underline">重新提交检测</Link></Center>
  }
  if (!data) {
    return <Center><Loader2 className="animate-spin text-indigo-400" size={32} /></Center>
  }

  if (data.status !== 'done' && data.status !== 'error') {
    const stageLabel: Record<string, string> = {
      parse: '解析文档', compare: '比对语料库', web: '联网全网核查',
      aigc: 'AIGC 多引擎分析', save: '生成报告',
    }
    const pct = progress?.pct ?? 8
    return (
      <Center>
        <Loader2 className="animate-spin text-indigo-500" size={36} />
        <p className="mt-4 font-medium text-slate-700">正在检测：{data.title}</p>
        <p className="mt-1 text-sm text-slate-400">
          {progress?.stage ? stageLabel[progress.stage] ?? progress.stage : '任务已受理'}…
        </p>
        <div className="mt-5 w-72 h-2.5 bg-slate-100 rounded-full overflow-hidden">
          <div className="h-full rounded-full bg-gradient-to-r from-indigo-400 to-indigo-600 transition-all duration-500"
            style={{ width: `${Math.max(6, Math.min(96, pct))}%` }} />
        </div>
        <p className="mt-2 text-xs text-slate-400">{pct}%</p>
      </Center>
    )
  }
  if (data.status === 'error') {
    return <Center><AlertTriangle className="text-red-400" size={36} />
      <p className="mt-3 text-slate-600">检测失败：{data.error}</p></Center>
  }

  const plag = data.report?.plagiarism
  const aigcEngines = data.report?.aigc?.engines ?? []
  const local = data.report?.aigc?.local
  const plagRate = plag?.total_rate ?? 0
  const aigcRate = local?.rate ?? 0

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      {/* 标题栏 */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <button onClick={() => history.back()} className="text-sm text-slate-400 hover:text-indigo-600 flex items-center gap-1 mb-2">
            <ArrowLeft size={14} /> 返回
          </button>
          <h1 className="text-xl md:text-2xl font-bold text-slate-800 truncate">{data.title}</h1>
          <p className="mt-1.5 text-xs text-slate-400">
            报告单号 {data.id} ｜ {data.created_at} ｜ 全文 {data.word_count} 字符 ｜ 语言 {data.language.toUpperCase()}
          </p>
        </div>
        <button
          onClick={exportReport}
          className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-800 text-white text-sm hover:bg-slate-700 transition-colors"
        >
          <Download size={15} /> 导出报告
        </button>
      </div>

      {/* 核心指标卡 */}
      <div className="mt-6 grid md:grid-cols-3 gap-4">
        {plag && (
          <div className="bg-white rounded-2xl border border-slate-200 p-6 flex items-center gap-5">
            <RingGauge value={plagRate} color={rateColor(plagRate)} label="" size={110} />
            <div>
              <div className="text-sm font-semibold text-slate-700">总文字复制比</div>
              <div className={`mt-1 inline-block px-2 py-0.5 rounded-md text-xs font-medium ${plagRate < 10 ? 'bg-emerald-50 text-emerald-600' : plagRate < 25 ? 'bg-amber-50 text-amber-600' : 'bg-red-50 text-red-600'}`}>
                {rateLabel(plagRate)}
              </div>
              <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                命中 {plag.matched_sentences}/{plag.sentence_count} 句<br />
                重复 {plag.dup_units} / 比对 {plag.total_units} 单位
                {typeof plag.quote_rate === 'number' && plag.quote_rate > 0 && (
                  <><br />其中规范引用 {plag.quote_rate}%（未计入复制比）</>
                )}
              </p>
            </div>
          </div>
        )}
        {local && (
          <div className="bg-white rounded-2xl border border-slate-200 p-6 flex items-center gap-5">
            <RingGauge value={aigcRate} color={aigcColor(aigcRate)} label="" size={110} />
            <div>
              <div className="text-sm font-semibold text-slate-700">AIGC 疑似度</div>
              <div className="mt-1 inline-block px-2 py-0.5 rounded-md bg-violet-50 text-violet-600 text-xs font-medium">
                {local.name}
              </div>
              <p className="mt-2 text-xs text-slate-400 leading-relaxed">
                AI 生成内容统计特征评分<br />
                {local.note}
              </p>
            </div>
          </div>
        )}
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <div className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
            <Gauge size={15} className="text-indigo-500" /> 检测配置
          </div>
          <ul className="mt-3 space-y-2 text-xs text-slate-500">
            <li>检测类型：{{ full: '综合检测', plagiarism: '仅查重', aigc: '仅 AIGC' }[data.report?.options?.mode ?? 'full']}</li>
            <li>参考文献剥离：{data.report?.options?.strip_references ? '已开启' : '关闭'}</li>
            <li>对比库：内置语料 + 自建文档库</li>
            {plag && <li>相似来源：{plag.sources.length} 个</li>}
          </ul>
        </div>
      </div>

      {/* 多引擎 AIGC 对比 */}
      {aigcEngines.length > 0 && (
        <div className="mt-4 bg-white rounded-2xl border border-slate-200 p-6">
          <h3 className="font-semibold text-slate-700 flex items-center gap-1.5 text-sm">
            <Bot size={15} className="text-violet-500" /> AIGC 多引擎对比
          </h3>
          <div className="mt-4 space-y-3">
            {aigcEngines.map(e => (
              <div key={e.key} className="flex items-center gap-3 text-sm">
                <span className="w-36 shrink-0 truncate text-slate-600">{e.name}</span>
                {e.status === 'ok' && e.rate !== null ? (
                  <>
                    <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full bg-gradient-to-r from-violet-400 to-violet-600 transition-all duration-700"
                        style={{ width: `${e.rate}%` }} />
                    </div>
                    <span className="w-12 text-right font-semibold" style={{ color: aigcColor(e.rate) }}>{e.rate}%</span>
                  </>
                ) : (
                  <>
                    <div className="flex-1 text-xs text-slate-400">
                      {e.status === 'not_configured' ? '未配置 API Key'
                        : e.status === 'error' ? `调用失败：${e.note}`
                        : e.status === 'experimental' ? '实验性 · 暂不可真实调用（未发送数据）'
                        : '需机构接口对接，无公开 API'}
                    </div>
                    <span className="w-12 text-right text-xs text-slate-300">—</span>
                  </>
                )}
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-400">
            提示：不同引擎的训练数据与算法差异较大，AIGC 率仅供参考，建议以多个引擎交叉验证。
          </p>
        </div>
      )}

      {/* Tabs */}
      <div className="mt-6 bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="flex border-b border-slate-100 overflow-x-auto">
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-5 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                tab === t.key
                  ? 'border-indigo-600 text-indigo-700 bg-indigo-50/40'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {t.label}
              {t.key === 'fragments' && plag && (
                <span className="ml-1.5 px-1.5 py-0.5 rounded bg-red-50 text-red-500 text-xs">{plag.fragments.length}</span>
              )}
            </button>
          ))}
        </div>

        <div className="p-6">
          {tab === 'overview' && <Overview data={data} />}
          {tab === 'fulltext' && <FullText data={data} />}
          {tab === 'fragments' && <Fragments data={data} />}
          {tab === 'web' && <WebCheckTab data={data} />}
          {tab === 'aigc' && <AigcDetail data={data} />}
        </div>
      </div>
    </div>
  )
}

function Center({ children }: { children: React.ReactNode }) {
  return <div className="py-32 text-center flex flex-col items-center">{children}</div>
}

/* ---------- 总览 ---------- */
function Overview({ data }: { data: CheckDetail }) {
  const plag = data.report?.plagiarism
  if (!plag) return <p className="text-sm text-slate-400">本次未启用查重。</p>
  const maxRate = Math.max(1, ...plag.sources.map(s => s.rate))

  return (
    <div className="space-y-8">
      <section>
        <h4 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
          <Copy size={14} className="text-indigo-500" /> 相似来源分布
        </h4>
        {plag.sources.length === 0 ? (
          <p className="mt-3 text-sm text-emerald-600">未检出相似来源，未发现与对比库重复的内容。</p>
        ) : (
          <div className="mt-4 space-y-3">
            {plag.sources.map((s, i) => (
              <div key={s.doc_id} className="flex items-center gap-3 text-sm">
                <span className="w-6 text-xs text-slate-400">[{i + 1}]</span>
                <span className="flex-1 truncate text-slate-600" title={s.title}>{s.title}</span>
                <div className="hidden sm:block w-48 h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-red-400/80 rounded-full" style={{ width: `${(s.rate / maxRate) * 100}%` }} />
                </div>
                <span className="w-14 text-right text-slate-500 text-xs">{s.dup_units} 字</span>
                <span className="w-14 text-right font-semibold text-red-500">{s.rate}%</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h4 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
          <FileSearch size={14} className="text-indigo-500" /> 全文重复热力（按句）
        </h4>
        <div className="mt-4 flex flex-wrap gap-1">
          {plag.sent_results.map((s, i) => (
            <div
              key={i}
              title={s.matched ? `重复：${s.best?.title}` : '原创'}
              className={`h-6 min-w-6 flex-1 rounded-sm ${
                s.matched ? 'bg-red-400/80' : 'bg-emerald-200/70'
              }`}
            />
          ))}
        </div>
        <div className="mt-2 flex items-center gap-4 text-xs text-slate-400">
          <span className="flex items-center gap-1"><i className="w-3 h-3 rounded-sm bg-red-400/80 inline-block" /> 重复句</span>
          <span className="flex items-center gap-1"><i className="w-3 h-3 rounded-sm bg-emerald-200/70 inline-block" /> 原创句</span>
        </div>
      </section>
    </div>
  )
}

/* ---------- 全文标红 ---------- */
function FullText({ data }: { data: CheckDetail }) {
  const plag = data.report?.plagiarism
  const local = data.report?.aigc?.local
  if (!plag) return <p className="text-sm text-slate-400">本次未启用查重。</p>
  const aigcMap = new Map<number, AigcSentence>()
  if (local) for (const s of local.sentence_scores) aigcMap.set(s.start, s)

  return (
    <div>
      <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 mb-4">
        <span className="flex items-center gap-1.5"><i className="mark-dup w-8 h-4 rounded-sm inline-block" /> 与对比库重复</span>
        <span className="flex items-center gap-1.5"><i className="mark-web w-8 h-4 rounded-sm inline-block" /> 联网核查命中（公开网页）</span>
        <span className="flex items-center gap-1.5"><i className="mark-aigc w-8 h-4 rounded-sm inline-block" /> AI 生成高度疑似</span>
      </div>
      <div className="rounded-xl bg-slate-50 border border-slate-100 p-5 text-[15px] leading-loose">
        {plag.sent_results.map((s, i) => {
          const aigc = aigcMap.get(s.start)
          const cls = s.matched ? 'mark-dup' : s.web ? 'mark-web' : aigc && aigc.level === 'high' ? 'mark-aigc' : ''
          const tip = s.matched
            ? `与「${s.best?.title}」相似 ${(100 * (s.best?.sim ?? 0)).toFixed(0)}%`
            : s.web ? `联网命中：${s.web.title}（${(100 * s.web.sim).toFixed(0)}%）`
            : aigc ? `AIGC 疑似分：${aigc.score}` : ''
          return (
            <span key={i} className={cls} title={tip}>{s.text}</span>
          )
        })}
      </div>
    </div>
  )
}

/* ---------- 联网核查 ---------- */
function WebCheckTab({ data }: { data: CheckDetail }) {
  const web = data.report?.plagiarism?.web
  if (!web) {
    return (
      <div className="text-center py-8">
        <Globe className="mx-auto text-slate-300" size={36} />
        <p className="mt-3 text-sm text-slate-500">本次检测未启用联网核查</p>
        <p className="mt-1 text-xs text-slate-400">提交时勾选「联网全网核查」，即可对可疑句做搜索引擎比对</p>
      </div>
    )
  }
  const statusMap = {
    ok: { label: '已完成', cls: 'bg-emerald-50 text-emerald-600' },
    partial: { label: '部分完成', cls: 'bg-amber-50 text-amber-600' },
    error: { label: '失败', cls: 'bg-red-50 text-red-600' },
  } as const
  const st = statusMap[web.status] ?? statusMap.ok

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`px-2.5 py-1 rounded-md text-xs font-medium ${st.cls}`}>{st.label}</span>
        <span className="text-sm text-slate-600">{web.note}</span>
        {web.failed > 0 && (
          <span className="text-xs text-red-500">{web.failed} 句检索失败</span>
        )}
        <div className="ml-auto text-right">
          <span className="text-2xl font-bold" style={{ color: '#c2410c' }}>{web.web_dup_rate}%</span>
          <span className="ml-1.5 text-xs text-slate-400">联网重复率</span>
        </div>
      </div>

      {web.sources.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-700">互联网命中来源</h4>
          <div className="mt-3 space-y-2">
            {web.sources.map((s, i) => (
              <div key={s.url} className="flex items-center gap-3 text-sm bg-slate-50 rounded-lg px-3 py-2">
                <span className="text-xs text-slate-400">[{i + 1}]</span>
                <a href={s.url} target="_blank" rel="noreferrer"
                  className="flex-1 truncate text-indigo-600 hover:underline flex items-center gap-1" title={s.title}>
                  {s.title} <ExternalLink size={12} className="shrink-0" />
                </a>
                <span className="text-xs text-slate-500">{s.hits} 句</span>
                <span className="w-14 text-right text-xs font-medium text-orange-500">{s.rate}%</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h4 className="text-sm font-semibold text-slate-700">命中片段明细</h4>
        {web.hits.length === 0 ? (
          <p className="mt-3 text-sm text-emerald-600">
            已核查 {web.checked} 个可疑句，未在公开网页中检出相似内容。
          </p>
        ) : (
          <div className="mt-3 space-y-4">
            {web.hits.map((h, i) => (
              <div key={i} className="border border-orange-200 rounded-xl overflow-hidden">
                <div className="px-4 py-2 bg-orange-50 border-b border-orange-100 flex items-center gap-2 text-xs">
                  <span className="px-2 py-0.5 rounded bg-orange-100 text-orange-600 font-semibold">联网片段 {i + 1}</span>
                  <a href={h.url} target="_blank" rel="noreferrer"
                    className="truncate text-indigo-600 hover:underline flex items-center gap-1 max-w-[45%]" title={h.title}>
                    {h.title} <ExternalLink size={11} className="shrink-0" />
                  </a>
                  <span className="ml-auto px-2 py-0.5 rounded bg-amber-100 text-amber-700 font-semibold">
                    {(h.sim * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-100">
                  <div className="p-4">
                    <div className="text-xs text-slate-400 mb-2">论文原文</div>
                    <p className="text-sm text-orange-700 bg-orange-50 rounded-lg p-3 leading-relaxed">{h.text}</p>
                  </div>
                  <div className="p-4">
                    <div className="text-xs text-slate-400 mb-2">网页原文摘录</div>
                    <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 leading-relaxed">{h.snippet || '（页面归一化后全文子串命中）'}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <p className="text-xs text-slate-400">
        联网核查覆盖公开网页（含部分 OA 论文页面），无法访问学位论文库、图书等非公开内容；
        商业查重系统的海量授权库仍是不可替代的定稿依据。
      </p>
    </div>
  )
}

/* ---------- 相似片段 ---------- */
function Fragments({ data }: { data: CheckDetail }) {
  const plag = data.report?.plagiarism
  if (!plag) return null
  if (plag.fragments.length === 0)
    return <p className="text-sm text-emerald-600 py-6 text-center">未检出相似片段，全部内容未与对比库命中。</p>

  return (
    <div className="space-y-4">
      {plag.fragments.map((f, i) => (
        <div key={i} className="border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center gap-2 text-xs">
            <span className="px-2 py-0.5 rounded bg-red-50 text-red-500 font-semibold">片段 {i + 1}</span>
            <span className="text-slate-400">重复 {f.dup_units} 字 ｜ 占全文 {f.rate}%</span>
          </div>
          <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-100">
            <div className="p-4">
              <div className="text-xs text-slate-400 mb-2">论文原文</div>
              <p className="text-sm text-red-600 bg-red-50 rounded-lg p-3 leading-relaxed">{f.text}</p>
            </div>
            <div className="p-4">
              <div className="text-xs text-slate-400 mb-2 flex items-center justify-between">
                <span>最相似来源：{f.best_source?.title}</span>
                <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-600 font-semibold">
                  {(100 * (f.best_source?.sim ?? 0)).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 leading-relaxed">{f.best_source?.src_text}</p>
              {f.all_sources && f.all_sources.length > 1 && (
                <details className="mt-2">
                  <summary className="text-xs text-indigo-500 cursor-pointer">其他来源（{f.all_sources.length - 1}）</summary>
                  <ul className="mt-2 space-y-1.5">
                    {f.all_sources.slice(1).map(s => (
                      <li key={s.doc_id} className="text-xs text-slate-500 bg-slate-50 rounded p-2">
                        <span className="font-medium text-slate-600">{s.title}</span>
                        <span className="ml-2 text-amber-600">{(100 * s.sim).toFixed(0)}%</span>
                        <p className="mt-1">{s.src_text}</p>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

/* ---------- AIGC 明细 ---------- */
function AigcDetail({ data }: { data: CheckDetail }) {
  const local = data.report?.aigc?.local
  if (!local) return <p className="text-sm text-slate-400">本次未启用 AIGC 检测。</p>

  const byLevel = { high: 0, mid: 0, low: 0 } as Record<string, number>
  for (const s of local.sentence_scores) byLevel[s.level]++
  const total = local.sentence_scores.length || 1

  return (
    <div className="grid md:grid-cols-2 gap-8">
      <div>
        <h4 className="text-sm font-semibold text-slate-700">六维特征雷达</h4>
        <p className="text-xs text-slate-400 mt-1 mb-2">数值越靠外，AI 生成统计特征越明显</p>
        <Radar features={local.features} />
        <div className="mt-4 flex justify-center gap-4 text-xs">
          <span className="text-red-500">高度疑似 {byLevel.high} 句</span>
          <span className="text-amber-500">疑似 {byLevel.mid} 句</span>
          <span className="text-emerald-500">低风险 {byLevel.low} 句</span>
        </div>
      </div>
      <div>
        <h4 className="text-sm font-semibold text-slate-700">逐句 AI 疑似度</h4>
        <p className="text-xs text-slate-400 mt-1 mb-3">分数 ≥ 70 高度疑似，45–70 疑似，&lt;45 低风险</p>
        <div className="max-h-[420px] overflow-y-auto pr-1 space-y-2.5">
          {local.sentence_scores.map((s, i) => (
            <div key={i} className="text-sm">
              <div className="flex items-start gap-2">
                <span
                  className={`mt-0.5 w-12 text-right text-xs font-bold shrink-0 ${
                    s.level === 'high' ? 'text-red-500' : s.level === 'mid' ? 'text-amber-500' : 'text-emerald-500'
                  }`}
                >
                  {s.score.toFixed(0)}
                </span>
                <div className="flex-1">
                  <p className="text-slate-600 leading-snug">{s.text}</p>
                  <div className="mt-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        s.level === 'high' ? 'bg-red-400' : s.level === 'mid' ? 'bg-amber-400' : 'bg-emerald-300'
                      }`}
                      style={{ width: `${s.score}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
