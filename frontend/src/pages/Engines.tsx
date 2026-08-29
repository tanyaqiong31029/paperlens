import { useEffect, useState } from 'react'
import { Bot, KeyRound, Info, CheckCircle2, CircleDashed, Globe } from 'lucide-react'
import { api, EngineInfo } from '../api'

export default function Engines() {
  const [engines, setEngines] = useState<EngineInfo[]>([])
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState('')

  const load = () => api.listEngines().then(setEngines)
  useEffect(() => { load() }, [])

  const save = async (key: string, enabled: boolean) => {
    setMsg('')
    try {
      await api.configEngine(key, keys[key] ?? '', enabled)
      setMsg('配置已保存，下次检测生效')
      load()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : '保存失败')
    }
  }

  const apiEngines = engines.filter(e => e.type === 'api')
  const searchEngines = engines.filter(e => e.type === 'search')
  const manualEngines = engines.filter(e => e.type === 'manual')

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-slate-800">AIGC 检测引擎</h1>
      <p className="mt-1.5 text-sm text-slate-500">
        本地引擎始终参与检测；国际引擎填入 API Key 后即可在每次检测中真实调用并汇总对比。
      </p>

      {msg && (
        <div className="mt-4 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm px-4 py-2.5">
          {msg}
        </div>
      )}

      <div className="mt-8 space-y-4">
        {/* 本地引擎 */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 flex gap-4">
          <div className="w-11 h-11 rounded-xl bg-indigo-600 text-white flex items-center justify-center shrink-0">
            <Bot size={22} />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-slate-800">本地集成引擎 v2</h3>
              <span className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-600 text-xs font-medium">内置 · 始终启用</span>
            </div>
            <p className="mt-1.5 text-sm text-slate-500 leading-relaxed">
              离线多信号集成：句长均匀度、套话密度、连接词规整度、词汇中庸度、标点单一度、句式模板化
              六维统计指纹 + 语料库 n-gram LM 的句间突发性 / token 困惑波动两个平滑度信号，
              输出全文级与句子级 AI 疑似度及特征雷达。方法细节见 README。
            </p>
          </div>
        </div>

        {/* 模型引擎插件 */}
        {engines.filter(e => e.type === 'model').map(e => (
          <div key={e.key} className="bg-white rounded-2xl border border-slate-200 p-6 flex gap-4">
            <div className="w-11 h-11 rounded-xl bg-violet-100 text-violet-600 flex items-center justify-center shrink-0">
              <Bot size={22} />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-slate-800">{e.name}</h3>
                {e.enabled ? (
                  <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-600 text-xs font-medium">已安装 · 自动启用</span>
                ) : (
                  <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-500 text-xs font-medium">未安装</span>
                )}
              </div>
              <p className="mt-1.5 text-sm text-slate-500 leading-relaxed">{e.desc}</p>
              {!e.enabled && (
                <pre className="mt-2 text-xs bg-slate-50 rounded-lg p-3 text-slate-600 overflow-x-auto">{`pip install "transformers>=4.40" torch
# 可选：指向自训模型（NLPCC'25 DetectRL-ZH / HC3-Chinese / M4 微调权重）
export AIGC_MODEL_ZH=你的中文检测模型
export AIGC_MODEL_EN=Hello-SimpleAI/chatgpt-detector-roberta`}</pre>
              )}
            </div>
          </div>
        ))}

        {/* API 引擎 */}
        {apiEngines.map(e => (
          <div key={e.key} className="bg-white rounded-2xl border border-slate-200 p-6">
            <div className="flex items-start gap-4">
              <div className="w-11 h-11 rounded-xl bg-slate-100 text-slate-500 flex items-center justify-center shrink-0">
                <KeyRound size={20} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-semibold text-slate-800">{e.name}</h3>
                  <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-500 text-xs">{e.region}</span>
                  {e.enabled ? (
                    <span className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
                      <CheckCircle2 size={13} /> 已启用
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-slate-400">
                      <CircleDashed size={13} /> 未启用
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-sm text-slate-500">{e.desc}</p>
                <div className="mt-3 flex flex-col sm:flex-row gap-2">
                  <input
                    type="password"
                    value={keys[e.key] ?? ''}
                    onChange={ev => setKeys({ ...keys, [e.key]: ev.target.value })}
                    placeholder={e.configured ? '已保存（输入可覆盖）' : '粘贴 API Key…'}
                    className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                  />
                  <button
                    onClick={() => save(e.key, true)}
                    className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-700"
                  >
                    保存并启用
                  </button>
                  {e.enabled && (
                    <button
                      onClick={() => save(e.key, false)}
                      className="px-4 py-2 rounded-lg border border-slate-200 text-slate-600 text-sm hover:bg-slate-50"
                    >
                      停用
                    </button>
                  )}
                </div>
                <p className="mt-2 text-xs text-slate-400">
                  Key 仅保存在本机服务端数据库。调用结果取决于服务官方接口的可用性与额度。
                </p>
              </div>
            </div>
          </div>
        ))}

        {/* 联网核查检索源 */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <div className="flex items-center gap-2 text-slate-700 font-medium">
            <Globe size={16} className="text-orange-500" />
            联网核查检索源（可选，用于「联网全网核查」）
          </div>
          <div className="mt-3 space-y-4">
            {searchEngines.map(e => (
              <div key={e.key} className="flex flex-col gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-slate-700">{e.name}</span>
                  {e.enabled ? (
                    <span className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
                      <CheckCircle2 size={13} /> 已启用
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-slate-400">
                      <CircleDashed size={13} /> 未启用（用 Bing/DuckDuckGo 网页检索兜底）
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400">{e.desc}</p>
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={keys[e.key] ?? ''}
                    onChange={ev => setKeys({ ...keys, [e.key]: ev.target.value })}
                    placeholder={e.configured ? '已保存（输入可覆盖）' : '粘贴 API Key…'}
                    className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                  />
                  <button
                    onClick={() => save(e.key, true)}
                    className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-700"
                  >
                    保存并启用
                  </button>
                  {e.enabled && (
                    <button
                      onClick={() => save(e.key, false)}
                      className="px-4 py-2 rounded-lg border border-slate-200 text-slate-600 text-sm hover:bg-slate-50"
                    >
                      停用
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 机构引擎说明 */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <div className="flex items-center gap-2 text-slate-700 font-medium">
            <Info size={16} className="text-slate-400" />
            主流机构级引擎（无公开 API，用于结果对照参考）
          </div>
          <ul className="mt-3 divide-y divide-slate-100">
            {manualEngines.map(e => (
              <li key={e.key} className="py-2.5 flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3">
                <span className="text-sm font-medium text-slate-700 w-44 shrink-0">{e.name}</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-500 text-xs w-fit">{e.region}</span>
                <span className="text-xs text-slate-400 sm:ml-auto sm:text-right max-w-sm">{e.desc}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
