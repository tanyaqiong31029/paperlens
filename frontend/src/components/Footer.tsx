export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white mt-12">
      <div className="max-w-6xl mx-auto px-4 py-6 text-xs text-slate-500 space-y-1.5">
        <p className="font-medium text-slate-600">PaperLens 论文检测中心</p>
        <p>
          本平台采用本地比对库与统计检测算法，检测结果仅供写作自查与修改参考，不代表任何官方机构的审查结论；
          定稿请以学校指定的查重系统（如知网、维普、万方、Turnitin）为准。
        </p>
        <p>内置语料均为演示用途的自建语料。请勿在检测中提交涉密或敏感内容。</p>
      </div>
    </footer>
  )
}
