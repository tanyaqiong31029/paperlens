import { useEffect, useRef, useState } from 'react'
import { BookOpen, Lock, Trash2, UploadCloud, Database } from 'lucide-react'
import { api, LibraryDoc } from '../api'

export default function Library() {
  const [docs, setDocs] = useState<LibraryDoc[]>([])
  const [loading, setLoading] = useState(true)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const load = () => api.listDocs().then(setDocs).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  const addByFile = async (f: File | null | undefined) => {
    if (!f) return
    setErr(''); setMsg('')
    try {
      const r = await api.addDocByFile(f, title)
      setMsg(`已加入对比库：${r.id}`)
      setTitle('')
      load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : '上传失败')
    }
  }

  const addByText = async () => {
    if (text.trim().length < 20) {
      setErr('文档内容至少 20 字符')
      return
    }
    setErr(''); setMsg('')
    try {
      await api.addDocByText(text, title)
      setMsg('已加入对比库')
      setTitle(''); setText('')
      load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : '添加失败')
    }
  }

  const remove = async (id: number) => {
    await api.deleteDoc(id)
    load()
  }

  const builtin = docs.filter(d => d.is_builtin)
  const userDocs = docs.filter(d => !d.is_builtin)

  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-800">对比文档库</h1>
      <p className="mt-1.5 text-sm text-slate-500">
        对比库决定"和谁比"。内置语料为演示数据；上传课题相关文献、往届论文即可建立私有比对库，命中更贴近真实场景。
      </p>

      {/* 添加文档 */}
      <div className="mt-8 bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
        <div className="flex items-center gap-2 text-slate-700 font-medium">
          <UploadCloud size={17} className="text-indigo-500" />
          添加对比文档
        </div>
        <input
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="文档标题（可选，默认取文件名/首行）"
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
        />
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => inputRef.current?.click()}
            className="flex-1 border-2 border-dashed border-slate-300 rounded-xl py-5 text-sm text-slate-500 hover:border-indigo-300 hover:bg-indigo-50/50 transition-colors flex items-center justify-center gap-2"
          >
            <UploadCloud size={17} /> 点击上传 docx / pdf / txt 文件
          </button>
          <input
            ref={inputRef}
            type="file"
            hidden
            accept=".docx,.pdf,.txt,.md"
            onChange={e => { addByFile(e.target.files?.[0]); e.target.value = '' }}
          />
        </div>
        <details className="text-sm">
          <summary className="cursor-pointer text-slate-500 hover:text-indigo-600">或直接粘贴文本</summary>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            rows={4}
            placeholder="粘贴需要纳入对比库的文本内容…"
            className="mt-2 w-full border border-slate-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
          />
          <button
            onClick={addByText}
            className="mt-2 px-4 py-2 rounded-lg bg-slate-800 text-white text-sm hover:bg-slate-700"
          >
            添加文本
          </button>
        </details>
        {err && <div className="text-sm text-red-600">{err}</div>}
        {msg && <div className="text-sm text-emerald-600">{msg}</div>}
      </div>

      {/* 文档列表 */}
      <div className="mt-6 grid lg:grid-cols-2 gap-6">
        <section className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3.5 border-b border-slate-100 flex items-center gap-2 text-sm font-medium text-slate-700">
            <Database size={15} className="text-indigo-500" /> 自建对比库
            <span className="ml-auto text-xs text-slate-400">{userDocs.length} 篇</span>
          </div>
          {userDocs.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-400">暂无自建文档，上传后即可参与查重比对</div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {userDocs.map(d => (
                <li key={d.id} className="px-5 py-3 flex items-center gap-3 text-sm">
                  <BookOpen size={15} className="text-slate-300 shrink-0" />
                  <span className="flex-1 truncate text-slate-700">{d.title}</span>
                  <span className="text-xs text-slate-400">{d.word_count} 字</span>
                  <button
                    onClick={() => remove(d.id)}
                    className="p-1.5 rounded-md text-slate-300 hover:text-red-500 hover:bg-red-50"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3.5 border-b border-slate-100 flex items-center gap-2 text-sm font-medium text-slate-700">
            <Lock size={15} className="text-slate-400" /> 内置演示语料
            <span className="ml-auto text-xs text-slate-400">{builtin.length} 篇（只读）</span>
          </div>
          <ul className="divide-y divide-slate-100 max-h-80 overflow-y-auto">
            {builtin.map(d => (
              <li key={d.id} className="px-5 py-3 flex items-center gap-3 text-sm">
                <BookOpen size={15} className="text-indigo-300 shrink-0" />
                <span className="flex-1 truncate text-slate-600">{d.title}</span>
                <span className="text-xs text-slate-400">{d.word_count} 字</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
