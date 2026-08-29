import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  FileSearch, Sparkles, FileText, Languages, ShieldCheck, Gauge, ArrowRight,
  Bot, ScanSearch, BarChart3,
} from 'lucide-react'
import { api, Stats } from '../api'

const features = [
  {
    icon: ScanSearch,
    title: '精准文本查重',
    desc: '基于句子级指纹与 n-gram 索引，中英文双语文法适配，自动剥离参考文献后比对，输出片段级重复率与相似来源对照。',
  },
  {
    icon: Bot,
    title: 'AIGC 多引擎检测',
    desc: '内置离线统计引擎，从句式均匀度、套话密度等六维特征识别 AI 生成内容；支持接入 GPTZero、CopyLeaks 等国际引擎交叉验证。',
  },
  {
    icon: FileText,
    title: '全文标红报告',
    desc: '知网式阅读体验：重复片段标红、AI 疑似句标紫，相似片段左右对照，支持一键导出独立 HTML 报告与打印存档。',
  },
  {
    icon: Languages,
    title: '中英双语支持',
    desc: '自动识别文档语言，中文按字粒度、英文按词粒度设计指纹算法，论文摘要、综述、正文均可检测。',
  },
]

const steps = [
  { icon: FileSearch, title: '提交文档', desc: '上传 docx / pdf / txt，或直接粘贴文本' },
  { icon: Gauge, title: '智能检测', desc: '查重与 AIGC 双引擎并行分析，秒级出结果' },
  { icon: BarChart3, title: '查看报告', desc: '重复率、AIGC 率、标红原文、降重参考一站获取' },
]

export default function Home() {
  const [stats, setStats] = useState<Stats | null>(null)
  useEffect(() => {
    api.stats().then(setStats).catch(() => {})
  }, [])

  return (
    <div>
      {/* Hero */}
      <section className="bg-gradient-to-b from-indigo-50 via-white to-white">
        <div className="max-w-6xl mx-auto px-4 py-16 md:py-24 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-100/70 text-indigo-700 text-xs font-medium mb-6">
            <Sparkles size={14} />
            查重 + AIGC 检测 · 双引擎一站式
          </div>
          <h1 className="text-3xl md:text-5xl font-bold text-slate-800 leading-tight">
            论文查重 · AI 生成检测
            <br className="hidden md:block" />
            <span className="text-indigo-600">提交后秒级出报告</span>
          </h1>
          <p className="mt-5 text-slate-500 max-w-2xl mx-auto md:text-lg">
            参考 PaperPass / 知网 / GPTZero 等主流产品的报告体系：
            总文字复制比、相似来源对照、全文标红，并叠加多引擎 AIGC 率对比，
            帮你在提交前发现风险。
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <Link
              to="/submit"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 text-white font-medium hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-600/20"
            >
              立即检测 <ArrowRight size={17} />
            </Link>
            <Link
              to="/engines"
              className="px-6 py-3 rounded-xl bg-white border border-slate-200 text-slate-700 font-medium hover:bg-slate-50 transition-colors"
            >
              了解 AIGC 引擎
            </Link>
          </div>
          {stats && (
            <div className="mt-12 grid grid-cols-3 max-w-xl mx-auto divide-x divide-slate-200">
              <div className="px-4">
                <div className="text-2xl font-bold text-slate-800">{stats.corpus.documents}</div>
                <div className="text-xs text-slate-500 mt-1">对比库文档（篇）</div>
              </div>
              <div className="px-4">
                <div className="text-2xl font-bold text-slate-800">{stats.corpus.units.toLocaleString()}</div>
                <div className="text-xs text-slate-500 mt-1">比对语料规模</div>
              </div>
              <div className="px-4">
                <div className="text-2xl font-bold text-slate-800">{stats.engines}</div>
                <div className="text-xs text-slate-500 mt-1">AIGC 检测引擎</div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* 功能特性 */}
      <section className="max-w-6xl mx-auto px-4 py-12">
        <h2 className="text-2xl font-bold text-center text-slate-800">核心能力</h2>
        <p className="text-center text-slate-500 mt-2 text-sm">从重复率到 AIGC 率，完整覆盖论文自查场景</p>
        <div className="mt-8 grid md:grid-cols-2 lg:grid-cols-4 gap-4">
          {features.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="bg-white rounded-2xl border border-slate-200 p-5 hover:shadow-md hover:border-indigo-200 transition-all">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center mb-4">
                <Icon size={20} />
              </div>
              <h3 className="font-semibold text-slate-800">{title}</h3>
              <p className="mt-2 text-sm text-slate-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 检测流程 */}
      <section className="max-w-6xl mx-auto px-4 py-12">
        <h2 className="text-2xl font-bold text-center text-slate-800">三步完成检测</h2>
        <div className="mt-8 grid md:grid-cols-3 gap-4">
          {steps.map(({ icon: Icon, title, desc }, i) => (
            <div key={title} className="relative bg-white rounded-2xl border border-slate-200 p-6">
              <span className="absolute top-5 right-6 text-4xl font-bold text-slate-100 select-none">
                {String(i + 1).padStart(2, '0')}
              </span>
              <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center mb-4">
                <Icon size={20} />
              </div>
              <h3 className="font-semibold text-slate-800">{title}</h3>
              <p className="mt-1.5 text-sm text-slate-500">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 提示 */}
      <section className="max-w-6xl mx-auto px-4 pb-16">
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 flex gap-3">
          <ShieldCheck className="text-amber-600 shrink-0 mt-0.5" size={20} />
          <div className="text-sm text-amber-800 leading-relaxed">
            <p className="font-medium">检测说明</p>
            <p className="mt-1">
              内置对比库为演示用自建语料，检测前可在「文档库」上传你所在团队 / 学校的文献作为私有对比库；
              AIGC 检测的本地引擎基于统计学特征启发式判断，结果仅供自查参考。
              定稿请以学校指定系统为准。
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}
