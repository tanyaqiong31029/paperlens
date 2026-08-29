import { NavLink } from 'react-router-dom'
import { FileSearch, History, Library, Sparkles, Home, Globe, Wand2 } from 'lucide-react'

const links = [
  { to: '/', label: '首页', icon: Home },
  { to: '/submit', label: '开始检测', icon: FileSearch },
  { to: '/reduce', label: '降重·降AIGC', icon: Wand2 },
  { to: '/history', label: '检测历史', icon: History },
  { to: '/library', label: '文档库', icon: Library },
  { to: '/crawl', label: '语料采集', icon: Globe },
  { to: '/engines', label: '引擎配置', icon: Sparkles },
]

export default function NavBar() {
  return (
    <header className="sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-slate-200">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        <NavLink to="/" className="flex items-center gap-2 font-bold text-lg text-indigo-700">
          <span className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center">
            <FileSearch size={18} />
          </span>
          PaperLens
          <span className="hidden sm:inline text-sm font-normal text-slate-500">论文检测中心</span>
        </NavLink>
        <nav className="flex items-center gap-1">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 font-medium'
                    : 'text-slate-600 hover:bg-slate-100'
                }`
              }
            >
              <Icon size={15} />
              <span className="hidden md:inline">{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}
