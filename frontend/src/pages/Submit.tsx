import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { UploadCloud, ClipboardType, Loader2, FileUp, Info, Globe } from 'lucide-react'
import { api } from '../api'

type InputMode = 'file' | 'text'

export default function Submit() {
  const nav = useNavigate()
  const [mode, setMode] = useState<InputMode>('file')
  const [detect, setDetect] = useState('full')
  const [stripRefs, setStripRefs] = useState(true)
  const [webCheck, setWebCheck] = useState(false)
  const [webCheckCount, setWebCheckCount] = useState(10)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const pickFile = (f: File | null | undefined) => {
    if (!f) return
    const ok = /\.(docx|pdf|txt|md)$/i.test(f.name)
    if (!ok) {
      setError('仅支持 .docx / .pdf / .txt / .md 格式')
      return
    }
    if (f.size > 15 * 1024 * 1024) {
      setError('文件大小不能超过 15MB')
      return
    }
    setError('')
    setFile(f)
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, ''))
  }

  const submit = async () => {
    setError('')
    if (mode === 'file' && !file) {
      setError('请先选择要检测的文档')
      return
    }
    if (mode === 'text' && text.trim().length < 50) {
      setError('粘贴的正文至少 50 字符')
      return
    }
    setBusy(true)
    try {
      const opts = { title, mode: detect, stripReferences: stripRefs, webCheck, webCheckCount }
      const r =
        mode === 'file'
          ? await api.createCheckByFile(file!, opts)
          : await api.createCheckByText(text, opts)
      nav(`/report/${r.check_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败')
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-800">提交检测</h1>
      <p className="mt-1.5 text-sm text-slate-500">
        综合检测将同时输出重复率与 AIGC 率，也可以单独选择其中一项。
      </p>

      <div className="mt-8 bg-white rounded-2xl border border-slate-200 p-6 space-y-6">
        {/* 输入方式 */}
        <div className="flex gap-2 p-1 bg-slate-100 rounded-xl w-fit">
          <button
            onClick={() => setMode('file')}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              mode === 'file' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500'
            }`}
          >
            <UploadCloud size={15} /> 上传文档
          </button>
          <button
            onClick={() => setMode('text')}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              mode === 'text' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500'
            }`}
          >
            <ClipboardType size={15} /> 粘贴文本
          </button>
        </div>

        {mode === 'file' ? (
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => { e.preventDefault(); setDragOver(false); pickFile(e.dataTransfer.files?.[0]) }}
            onClick={() => inputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
              dragOver ? 'border-indigo-400 bg-indigo-50' : 'border-slate-300 hover:border-indigo-300 hover:bg-slate-50'
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              hidden
              accept=".docx,.pdf,.txt,.md"
              onChange={e => pickFile(e.target.files?.[0])}
            />
            <FileUp className="mx-auto text-indigo-400" size={36} />
            {file ? (
              <p className="mt-3 text-sm font-medium text-slate-700">{file.name}</p>
            ) : (
              <>
                <p className="mt-3 text-sm font-medium text-slate-600">点击选择或拖拽文件到此处</p>
                <p className="mt-1 text-xs text-slate-400">支持 docx / pdf / txt / md，15MB 以内</p>
              </>
            )}
          </div>
        ) : (
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder="在此粘贴论文正文…（至少 50 字符）"
            rows={9}
            className="w-full border border-slate-200 rounded-xl p-4 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 resize-y"
          />
        )}

        {/* 检测选项 */}
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">检测类型</label>
            <select
              value={detect}
              onChange={e => setDetect(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
            >
              <option value="full">综合检测（查重 + AIGC）</option>
              <option value="plagiarism">仅查重</option>
              <option value="aigc">仅 AIGC 检测</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">文档标题（可选）</label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="默认取文件名 / 首行"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
            />
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={stripRefs}
            onChange={e => setStripRefs(e.target.checked)}
            className="accent-indigo-600"
          />
          剔除文末「参考文献 / References / 致谢」后比对（不计入重复率）
        </label>

        {/* 联网全网核查 */}
        <div className={`rounded-xl border p-4 transition-colors ${webCheck ? 'border-orange-300 bg-orange-50/60' : 'border-slate-200 bg-slate-50/60'}`}>
          <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
            <input
              type="checkbox"
              checked={webCheck}
              onChange={e => setWebCheck(e.target.checked)}
              className="accent-orange-500"
            />
            <Globe size={15} className="text-orange-500" />
            联网全网核查（搜索引擎比对公开网页）
          </label>
          {webCheck && (
            <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
              <span className="text-slate-600">核查句数</span>
              <input
                type="number"
                min={3}
                max={30}
                value={webCheckCount}
                onChange={e => setWebCheckCount(Number(e.target.value) || 10)}
                className="w-20 border border-slate-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-orange-400/40"
              />
              <span className="text-xs text-slate-400">
                对本地库未命中的可疑句做精确短语检索并抓取页面比对，每句约 3-6 秒
              </span>
            </div>
          )}
          <p className="mt-2 text-xs text-slate-400">
            未配置检索 API Key 时使用 Bing / DuckDuckGo 网页检索兜底，受网络环境影响可能失败；
            可在「引擎配置」页填入 Bing API / SerpAPI Key 提高稳定性。
          </p>
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-2.5">{error}</div>
        )}

        <button
          onClick={submit}
          disabled={busy}
          className="w-full py-3 rounded-xl bg-indigo-600 text-white font-medium hover:bg-indigo-700 disabled:opacity-60 transition-colors flex items-center justify-center gap-2"
        >
          {busy && <Loader2 size={17} className="animate-spin" />}
          {busy ? '正在提交…' : '开始检测'}
        </button>

        <div className="flex gap-2 text-xs text-slate-400 items-start">
          <Info size={13} className="mt-0.5 shrink-0" />
          <p>检测在服务端后台执行，完成后自动跳转报告页；大文档解析可能需要数秒。</p>
        </div>
      </div>
    </div>
  )
}
