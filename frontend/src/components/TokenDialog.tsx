import { useState } from 'react'
import { KeyRound, X } from 'lucide-react'
import { clearAdminToken, getAdminToken, setAdminToken } from '../api'

interface Props {
  onClose: () => void
}

/** 管理员令牌输入框：仅局域网/令牌模式下需要；令牌只存 sessionStorage。 */
export default function TokenDialog({ onClose }: Props) {
  const [value, setValue] = useState(getAdminToken())
  const [error, setError] = useState('')

  const save = () => {
    if (!value.trim()) {
      setError('令牌不能为空（留空可用「清除」回到纯本机模式）')
      return
    }
    setAdminToken(value)
    onClose()
    window.location.reload()  // 让当前页面的查询用新令牌重发
  }

  const clear = () => {
    clearAdminToken()
    onClose()
    window.location.reload()
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-2 mb-4">
          <KeyRound size={18} className="text-indigo-600" />
          <h2 className="font-semibold text-slate-800">管理员令牌</h2>
          <button onClick={onClose} className="ml-auto p-1 rounded-md text-slate-400 hover:bg-slate-100">
            <X size={16} />
          </button>
        </div>
        <p className="text-xs text-slate-500 leading-relaxed mb-4">
          服务端启用了 <code className="bg-slate-100 px-1 rounded">PAPERLENS_ADMIN_TOKEN</code>{' '}
          时（通常是局域网/公网部署），需要在此填入令牌才能提交检测、查看报告和管理语料。
          令牌仅保存在本标签页的 sessionStorage，关闭标签页即清除，不会写入磁盘。
        </p>
        <input
          type="password"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && save()}
          placeholder="粘贴管理员令牌…"
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
          autoFocus
        />
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        <div className="mt-4 flex gap-2 justify-end">
          <button onClick={clear} className="px-3 py-2 rounded-lg border border-slate-200 text-slate-600 text-sm hover:bg-slate-50">
            清除令牌
          </button>
          <button onClick={save} className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-700">
            保存并重试
          </button>
        </div>
      </div>
    </div>
  )
}
