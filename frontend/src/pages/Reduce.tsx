import { useEffect, useState } from 'react'
import { Wand2, Copy, Download, ArrowRight, ShieldAlert } from 'lucide-react'
import { api } from '../api'

interface ReduceResult {
  mode: string
  language: string
  sentence_count: number
  changed_count: number
  before: { plagiarism: number | null; aigc: number | null }
  after: { plagiarism: number | null; aigc: number | null }
  segments: { start: number; end: number; orig: string; new: string; reasons: string[] }[]
  full_text: string
  note: string
}

type Mode = 'both' | 'dedup' | 'humanize'

const MODES: { key: Mode; label: string; desc: string }[] = [
  { key: 'both', label: '降重 + 降AIGC', desc: '同时压低重复率与 AIGC 率' },
  { key: 'dedup', label: '仅降重', desc: '只改写查重命中的句子（同义替换+长句切分）' },
  { key: 'humanize', label: '仅降AIGC', desc: '只改写 AI 疑似句（套话改写+连接词稀释+切分）' },
]

function Metric({ label, before, after, color }: { label: string; before: number | null; after: number | null; color: string }) {
  if (before === null || after === null) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-5 opacity-50">
        <div className="text-sm text-slate-500">{label}</div>
        <div className="text-xs text-slate-400 mt-2">本次模式未涉及</div>
      </div>
    )
  }
  const delta = Math.round((after - before) * 10) / 10
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-2 flex items-baseline gap-2.5">
        <span className="text-2xl font-bold text-slate-400">{before}%</span>
        <ArrowRight size={16} className="text-slate-300" />
        <span className="text-3xl font-bold" style={{ color }}>{after}%</span>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-md ${delta <= 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-500'}`}>
          {delta > 0 ? '+' : ''}{delta}
        </span>
      </div>
    </div>
  )
}

export default function Reduce() {
  const [text, setText] = useState('')
  const [mode, setMode] = useState<Mode>('both')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ReduceResult | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem('reduce_text')
    if (saved) setText(saved)
  }, [])
  useEffect(() => {
    const t = setTimeout(() => localStorage.setItem('reduce_text', text), 600)
    return () => clearTimeout(t)
  }, [text])

  const run = async () => {
    setError('')
    if (text.trim().length < 50) {
      setError('正文至少 50 字符')
      return
    }
    setBusy(true)
    setResult(null)
    try {
      const res = await fetch('/api/reduce', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, mode }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        throw new Error(j.detail || `请求失败 (${res.status})`)
      }
      setResult(await res.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : '请求失败')
    } finally {
      setBusy(false)
    }
  }

  const copyOut = async () => {
    if (!result) return
    await navigator.clipboard.writeText(result.full_text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const download = () => {
    if (!result) return
    const blob = new Blob([result.full_text], { type: 'text/plain;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'rewritten.txt'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-800">降重 · 降AIGC</h1>
      <p className="mt-1.5 text-sm text-slate-500 leading-relaxed">
        粘贴文本后自动定位查重命中句与 AI 疑似句，规则改写引擎给出逐句修改建议
        （同义替换、套话改写、连接词稀释、长句切分），改完立即用同一套引擎复测对比。
      </p>

      <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3.5 flex gap-2.5 text-xs text-amber-800 leading-relaxed">
        <ShieldAlert size={15} className="shrink-0 mt-0.5" />
        <p>
          规则引擎只做表达层修改，供<strong>修改你自己撰写或合法引用改写的段落</strong>使用；
          不得用于搬运他人成果后规避检测。改写结果请逐句人工复核，语义责任在作者。
        </p>
      </div>

      <div className="mt-6 bg-white rounded-2xl border border-slate-200 p-6 space-y-5">
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          rows={8}
          placeholder="粘贴需要降重 / 降AIGC 的段落…（至少 50 字符）"
          className="w-full border border-slate-200 rounded-xl p-4 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400"
        />
        <div className="flex flex-wrap gap-2">
          {MODES.map(m => (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              title={m.desc}
              className={`px-4 py-2 rounded-xl text-sm font-medium border transition-colors ${
                mode === m.key
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
              }`}
            >
              {m.label}
            </button>
          ))}
          <button
            onClick={run}
            disabled={busy}
            className="ml-auto px-6 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-60 flex items-center gap-2"
          >
            <Wand2 size={15} className={busy ? 'animate-pulse' : ''} />
            {busy ? '改写中…' : '生成改写建议'}
          </button>
        </div>
        {error && <div className="rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-2.5">{error}</div>}
      </div>

      {result && (
        <div className="mt-6 space-y-6">
          <div className="grid sm:grid-cols-2 gap-4">
            <Metric label="重复率（对比库）" before={result.before.plagiarism} after={result.after.plagiarism} color="#16a34a" />
            <Metric label="AIGC 率（本地引擎）" before={result.before.aigc} after={result.after.aigc} color="#7c3aed" />
          </div>

          <div className="bg-white rounded-2xl border border-slate-200">
            <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-3 text-sm">
              <span className="font-medium text-slate-700">逐句改写建议</span>
              <span className="text-xs text-slate-400">
                共 {result.sentence_count} 句，建议修改 {result.changed_count} 句
              </span>
              <div className="ml-auto flex gap-2">
                <button onClick={copyOut}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 flex items-center gap-1">
                  <Copy size={12} /> {copied ? '已复制' : '复制改写全文'}
                </button>
                <button onClick={download}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 flex items-center gap-1">
                  <Download size={12} /> 下载 txt
                </button>
              </div>
            </div>
            {result.segments.length === 0 ? (
              <div className="p-10 text-center text-sm text-slate-400">
                没有需要改写的句子（或该模式未命中目标句子）
              </div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {result.segments.map((seg, i) => (
                  <li key={i} className="p-5 space-y-2.5">
                    <p className="text-sm text-red-600/90 bg-red-50/70 rounded-lg p-3 leading-relaxed line-through decoration-red-300">
                      {seg.orig}
                    </p>
                    <p className="text-sm text-emerald-700 bg-emerald-50/70 rounded-lg p-3 leading-relaxed">
                      {seg.new}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {seg.reasons.map((r, j) => (
                        <span key={j} className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-600 text-xs">{r}</span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="text-xs text-slate-400">{result.note}</p>
        </div>
      )}
    </div>
  )
}
