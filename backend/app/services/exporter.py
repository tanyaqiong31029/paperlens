"""自包含 HTML 查重报告导出（知网/PaperPass 报告样式：总览环 + 标红全文 + 片段对照）。"""
import html
import json
from datetime import datetime

from .. import config, db


def export_html(check_id: str) -> str | None:
    row = db.get_check(check_id)
    if not row or not row["report"]:
        return None
    report = json.loads(row["report"])
    plag = report.get("plagiarism") or {}
    aigc_local = (report.get("aigc") or {}).get("local") or {}
    engines = (report.get("aigc") or {}).get("engines") or []

    rate = plag.get("total_rate", 0)
    aigc_rate = aigc_local.get("total_rate", 0)
    rate_color = _rate_color(rate)

    sent_results = plag.get("sent_results") or []
    body_parts = []
    for s in sent_results:
        esc = html.escape(s["text"])
        if s.get("matched"):
            body_parts.append(
                f'<mark class="dup" title="{html.escape(s["best"]["title"], quote=True)}">{esc}</mark>'
            )
        elif s.get("web"):
            body_parts.append(
                f'<mark class="web" title="联网命中：{html.escape(s["web"]["title"], quote=True)}">{esc}</mark>'
            )
        else:
            body_parts.append(esc)
    body_html = "".join(body_parts).replace("\n", "<br/>")

    web = plag.get("web") or {}
    web_rows = []
    for i, h in enumerate(web.get("hits", []), 1):
        web_rows.append(
            f"<tr><td>{i}</td><td class='frag'>{html.escape(h['text'][:160])}</td>"
            f"<td><a href='{html.escape(h['url'], quote=True)}' target='_blank'>{html.escape(h['title'][:80])}</a><br/>"
            f"<small>相似度 {h['sim']:.0%}</small></td>"
            f"<td class='frag'>{html.escape(h.get('snippet', '')[:160])}</td></tr>"
        )
    web_section = ""
    if web:
        status_label = {"ok": "已完成", "partial": "部分完成", "error": "失败"}.get(web.get("status"), web.get("status"))
        web_section = f"""
<h2>联网全网核查 <small style="color:#64748b;font-size:12px">（{status_label} · 检索源 {html.escape(str(web.get('provider','')))} · {html.escape(str(web.get('note','')))}）</small></h2>
<p>联网重复率：<b style="color:#c2410c">{web.get('web_dup_rate', 0)}%</b>（命中 {len(web.get('hits', []))} 句 / 核查 {web.get('checked', 0)} 句）</p>
<table><tr><th>#</th><th>论文片段</th><th>互联网来源</th><th>来源页面原文</th></tr>
{''.join(web_rows) or '<tr><td colspan="4">未在公开网页中检出相似内容</td></tr>'}</table>"""

    frag_rows = []
    for i, f in enumerate(plag.get("fragments", []), 1):
        src = f.get("best_source") or {}
        frag_rows.append(
            f"<tr><td>{i}</td>"
            f'<td class="frag">{html.escape(f["text"][:200])}</td>'
            f'<td>{html.escape(src.get("title", "-"))}<br/>'
            f'<small>相似度 {src.get("sim", 0):.0%}</small></td>'
            f"<td>{f.get('rate', 0)}%</td></tr>"
        )

    src_rows = []
    for i, s in enumerate(plag.get("sources", []), 1):
        src_rows.append(
            f"<tr><td>{i}</td><td>{html.escape(s['title'])}</td>"
            f"<td>{s['dup_units']} 字</td><td>{s['rate']}%</td></tr>"
        )

    engine_rows = []
    for e in engines:
        status_map = {
            "ok": '<span class="ok">已检测</span>',
            "not_configured": "未配置 API Key",
            "error": "调用失败",
            "manual": "需机构接口",
        }
        rate_cell = f"{e['rate']}%" if e.get("rate") is not None else "—"
        engine_rows.append(
            f"<tr><td>{html.escape(e['name'])}</td><td>{e['region']}</td>"
            f"<td>{rate_cell}</td><td>{status_map.get(e['status'], e['status'])}</td>"
            f"<td>{html.escape(e.get('note', ''))}</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"/>
<title>{html.escape(row['title'])} - 检测报告</title>
<style>
 body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1e293b;line-height:1.7}}
 h1{{font-size:22px}} h2{{font-size:17px;border-left:4px solid #2563eb;padding-left:8px;margin-top:32px}}
 .meta{{color:#64748b;font-size:13px}}
 .cards{{display:flex;gap:16px;margin:16px 0}}
 .card{{flex:1;border:1px solid #e2e8f0;border-radius:12px;padding:16px;text-align:center}}
 .big{{font-size:34px;font-weight:700}}
 table{{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}}
 th,td{{border:1px solid #e2e8f0;padding:8px;text-align:left;vertical-align:top}}
 th{{background:#f1f5f9}}
 .frag{{max-width:420px}}
 mark.dup{{background:#fecaca;color:#b91c1c;padding:1px 0}}
 mark.web{{background:#fed7aa;color:#c2410c;padding:1px 0}}
 .ok{{color:#16a34a;font-weight:600}}
 footer{{margin-top:40px;color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0;padding-top:12px}}
</style></head><body>
<h1>{html.escape(row['title'])}</h1>
<p class="meta">检测时间：{row['created_at']} ｜ 语言：{row['language']} ｜ 全文：{row['word_count']} 字符 ｜ 报告单号：{check_id}</p>
<div class="cards">
 <div class="card"><div class="big" style="color:{rate_color}">{rate}%</div><div>总文字复制比（重复率）</div></div>
 <div class="card"><div class="big" style="color:#7c3aed">{aigc_rate}%</div><div>AIGC 疑似度（本地引擎）</div></div>
 <div class="card"><div class="big" style="color:#0891b2">{plag.get('total_units', 0)}</div><div>参与比对字数</div></div>
</div>
<h2>相似来源</h2><table><tr><th>#</th><th>来源</th><th>重复字数</th><th>占比</th></tr>{''.join(src_rows) or '<tr><td colspan="4">未检出相似来源</td></tr>'}</table>
<h2>相似片段明细</h2><table><tr><th>#</th><th>论文片段</th><th>最相似来源</th><th>占比</th></tr>{''.join(frag_rows) or '<tr><td colspan="4">未检出相似片段</td></tr>'}</table>
{web_section}
<h2>AIGC 多引擎结果</h2><table><tr><th>引擎</th><th>区域</th><th>AIGC 率</th><th>状态</th><th>说明</th></tr>{''.join(engine_rows)}</table>
<h2>全文标红</h2><div>{body_html}</div>
<footer>{config.APP_NAME} v{config.APP_VERSION} ｜ 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 本报告仅供写作自查参考，定稿请以学校指定系统为准</footer>
</body></html>"""


def _rate_color(rate: float) -> str:
    if rate < 10:
        return "#16a34a"
    if rate < 25:
        return "#d97706"
    return "#dc2626"
