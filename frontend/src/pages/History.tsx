import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Trash2, Clock, FileText, History as HistoryIcon } from 'lucide-react'
import { api, CheckListItem } from '../api'

export default function History() {
  const nav = useNavigate()
  const [items, setItems] = useState<CheckListItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = () => api.listChecks().then(setItems).finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  const remove = async (id: string) => {
    await api.deleteCheck(id)
    load()
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-800">检测历史</h1>
      <p className="mt-1.5 text-sm text-slate-500">所有检测报告保留在本机服务端，可随时回看或删除。</p>

      <div className="mt-8 bg-white rounded-2xl border border-slate-200 overflow-hidden">
        {loading ? (
          <div className="p-10 text-center text-slate-400 text-sm">加载中…</div>
        ) : items.length === 0 ? (
          <div className="p-14 text-center">
            <HistoryIcon className="mx-auto text-slate-300" size={40} />
            <p className="mt-3 text-slate-500 text-sm">还没有检测记录</p>
            <button
              onClick={() => nav('/submit')}
              className="mt-4 px-5 py-2 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-700"
            >
              去检测第一篇论文
            </button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-slate-500 text-left">
                <th className="px-5 py-3 font-medium">文档</th>
                <th className="px-5 py-3 font-medium hidden sm:table-cell">字数</th>
                <th className="px-5 py-3 font-medium hidden md:table-cell">语言</th>
                <th className="px-5 py-3 font-medium hidden md:table-cell">状态</th>
                <th className="px-5 py-3 font-medium">时间</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map(it => (
                <tr
                  key={it.id}
                  className="hover:bg-indigo-50/40 cursor-pointer"
                  onClick={() => nav(`/report/${it.id}`)}
                >
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2.5">
                      <FileText size={16} className="text-indigo-400 shrink-0" />
                      <span className="font-medium text-slate-700 max-w-[300px] truncate">{it.title}</span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5 text-slate-500 hidden sm:table-cell">{it.word_count}</td>
                  <td className="px-5 py-3.5 hidden md:table-cell">
                    <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-xs uppercase">
                      {it.language}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 hidden md:table-cell">
                    {it.status === 'done' ? (
                      <span className="text-emerald-600 text-xs font-medium">完成</span>
                    ) : it.status === 'error' ? (
                      <span className="text-red-600 text-xs font-medium">失败</span>
                    ) : (
                      <span className="text-amber-600 text-xs font-medium">检测中</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-slate-400 text-xs whitespace-nowrap">
                    <Clock size={12} className="inline mr-1" />
                    {it.created_at}
                  </td>
                  <td className="px-3 py-3.5 text-right" onClick={e => e.stopPropagation()}>
                    <button
                      onClick={() => remove(it.id)}
                      className="p-2 rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                      title="删除记录"
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
