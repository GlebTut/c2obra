#!/usr/bin/env python3
"""
C Testing Coverage Tool - Report Generator
Reads branch_map.json + coverage.json and outputs HTML + CSV + source HTML reports
"""

import sys, json, os, csv, re
from datetime import datetime


def load_branch_map(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: branch map not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: branch map is malformed JSON: {e}")
        sys.exit(1)


def load_coverage(path):
    if not os.path.exists(path):
        print("⚠️  Warning: coverage file not found — treating all branches as uncovered")
        return {}
    with open(path) as f:
        data = json.load(f)
    return {int(e["id"]): e for e in data.get("branches", [])}


def merge(branch_map_data, coverage):
    rows = []
    for b in branch_map_data.get("branches", []):
        bid         = b["id"]
        hits        = coverage.get(int(bid), {})
        true_count  = hits.get("true",  0)
        false_count = hits.get("false", 0)
        covered     = hits["covered"] if "covered" in hits else (true_count > 0 and false_count > 0)
        rows.append({
            "branch_id":   bid,
            "line":        b.get("line",  "?"),
            "type":        b.get("type",  "?"),
            "label":       b.get("label", ""),
            "true_count":  true_count,
            "false_count": false_count,
            "covered":     covered,
        })
    return rows


def write_csv(rows, output_path, source_file):
    try:
        with open(output_path, "w", newline="") as f:
            has_labels = any(r.get("label") for r in rows)
            fieldnames = ["file", "branch_id", "line", "type"]
            if has_labels:
                fieldnames.append("label")
            fieldnames += ["true_count", "false_count", "covered"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                row = {"file": source_file, "branch_id": r["branch_id"],
                       "line": r["line"], "type": r["type"],
                       "true_count": r["true_count"], "false_count": r["false_count"],
                       "covered": r["covered"]}
                if has_labels:
                    row["label"] = r.get("label", "")
                writer.writerow(row)
            total_edges   = len(rows) * 2
            covered_edges = sum(1 for r in rows if r["true_count"]  > 0) + \
                            sum(1 for r in rows if r["false_count"] > 0)
            pct = (covered_edges / total_edges * 100) if total_edges > 0 else 0
            summary = {"file": "SUMMARY", "branch_id": "", "line": "", "type": "",
                       "true_count": "", "false_count": "",
                       "covered": f"{pct:.1f}% ({covered_edges}/{total_edges} edges)"}
            if has_labels:
                summary["label"] = ""
            writer.writerow(summary)
        print(f"✓ Wrote CSV to {output_path}")
    except OSError as e:
        print(f"❌ Error: could not write {output_path}: {e}")
        sys.exit(1)


def highlight_c_syntax(code):
    """Apply VS Code-like syntax highlighting via HTML spans."""
    keywords = r'\b(int|char|float|double|void|return|if|else|for|while|do|switch|case|default|break|continue|struct|typedef|static|const|unsigned|signed|long|short|extern|include|define|endif|ifdef|ifndef|printf|NULL)\b'
    token_re = re.compile(
        r'(//[^\n]*'
        r'|/\*[\s\S]*?\*/'
        r'|"(?:\\.|[^"\\])*"'
        r"|'(?:\\.|[^'\\])*'"
        r'|#\s*\w+'
        r'|\b\d+\b'
        r'|[a-zA-Z_]\w*'
        r'|.)'
    )
    out = ""
    for m in token_re.finditer(code):
        tok = m.group(0)
        if tok.startswith("//") or tok.startswith("/*"):
            out += f'<span style="color:#6a9955">{tok}</span>'
        elif tok.startswith('"') or tok.startswith("'"):
            out += f'<span style="color:#ce9178">{tok}</span>'
        elif tok.startswith("#"):
            out += f'<span style="color:#c586c0">{tok}</span>'
        elif re.fullmatch(r'\d+', tok):
            out += f'<span style="color:#b5cea8">{tok}</span>'
        elif re.fullmatch(keywords, tok):
            out += f'<span style="color:#569cd6">{tok}</span>'
        else:
            out += tok
    return out


def write_source_html(rows, branch_map_data, source_html_path, report_html_name):
    """Generate a separate _source.html with VS Code-style highlighted source."""
    src_path = branch_map_data.get("source_file", "")
    if not src_path or not os.path.exists(src_path):
        return False

    line_status = {}
    for r in rows:
        if r["line"] == "?":
            continue
        ln = int(r["line"])
        if r["covered"]:
            line_status[ln] = ("full", r["branch_id"])
        elif r["true_count"] > 0 or r["false_count"] > 0:
            line_status[ln] = ("partial", r["branch_id"])
        else:
            line_status[ln] = ("none", r["branch_id"])

    with open(src_path, errors="replace") as f:
        source_lines = f.readlines()

    lines_html = ""
    for i, raw_line in enumerate(source_lines, start=1):
        escaped     = (raw_line.rstrip()
                       .replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;"))
        highlighted = highlight_c_syntax(escaped)
        info        = line_status.get(i)

        if info:
            status, bid = info
            bg      = {"full": "#1a3a1a", "partial": "#3a2a00", "none": "#3a0a0a"}[status]
            border  = {"full": "#16a34a", "partial": "#d97706", "none": "#dc2626"}[status]
            badge_c = {"full": "#16a34a", "partial": "#d97706", "none": "#dc2626"}[status]
            badge_t = {"full": "●FULL",   "partial": "◐PART",   "none": "○NONE"}[status]
            badge   = f'<span style="float:right;font-size:0.7rem;color:{badge_c};padding-right:1rem">{badge_t}</span>'
            lines_html += (
                f'<div id="line-{i}" class="src-line" '
                f'style="background:{bg};border-left:3px solid {border}">'
                f'<span class="ln">{i:4}</span>'
                f'<span class="cd">{highlighted}</span>'
                f'{badge}'
                f'</div>'
            )
        else:
            lines_html += (
                f'<div id="line-{i}" class="src-line">'
                f'<span class="ln">{i:4}</span>'
                f'<span class="cd">{highlighted}</span>'
                f'</div>'
            )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Source — {os.path.basename(src_path)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #1e1e1e;
    color: #d4d4d4;
    font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 0.82rem;
    padding: 1rem 2rem;
  }}
  .topbar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #333;
  }}
  .topbar a {{ color: #569cd6; text-decoration: none; font-size: 0.85rem; }}
  .topbar a:hover {{ text-decoration: underline; }}
  .legend {{ font-size: 0.75rem; color: #888; display: flex; gap: 1rem; }}
  .legend span {{ display: flex; align-items: center; gap: 0.3rem; }}
  pre {{
    background: #1e1e1e;
    border-radius: 6px;
    overflow-x: auto;
    padding: 0.5rem 0;
  }}
  .src-line {{
    display: block;
    white-space: pre;
    line-height: 1.4;
    padding: 0 0.5rem;
    border-left: 3px solid transparent;
  }}
  .src-line:target {{
    outline: 2px solid #569cd6;
    border-radius: 2px;
    animation: pulse 1.2s ease;
  }}
  @keyframes pulse {{
    0%   {{ background: #264f78 !important; }}
    100% {{ background: inherit; }}
  }}
  .ln {{
    color: #444;
    user-select: none;
    margin-right: 1.5rem;
    display: inline-block;
    min-width: 2.5rem;
    text-align: right;
  }}
  .cd {{ color: #d4d4d4; }}
</style>
</head>
<body>
<div class="topbar">
  <a href="{report_html_name}">← Back to Report</a>
  <span style="color:#888;font-size:0.85rem">{os.path.basename(src_path)}</span>
  <div class="legend">
    <span><span style="color:#16a34a">●</span> FULL</span>
    <span><span style="color:#d97706">◐</span> PARTIAL</span>
    <span><span style="color:#dc2626">○</span> NONE</span>
  </div>
</div>
<pre>{lines_html}</pre>
</body>
</html>"""

    with open(source_html_path, "w") as f:
        f.write(html)
    print(f"✓ Wrote source view to {source_html_path}")
    return True


def write_html(rows, output_path, source_file, source_html_name=None):
    total_edges   = len(rows) * 2
    covered_true  = sum(1 for r in rows if r["true_count"]  > 0)
    covered_false = sum(1 for r in rows if r["false_count"] > 0)
    covered_edges = covered_true + covered_false
    pct      = (covered_edges / total_edges * 100) if total_edges > 0 else 0
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    bar_color = "#16a34a" if pct >= 80 else "#d97706" if pct >= 50 else "#dc2626"

    back_button = '<a href="summary_report.html" style="display:inline-block;margin-bottom:1.2rem;padding:0.45rem 1.1rem;background:#1a1a2e;color:#fff;border-radius:6px;text-decoration:none;font-size:0.88rem;font-weight:500;">← Back to Summary</a>'

    source_btn = ""
    if source_html_name:
        source_btn = f' <a href="{source_html_name}" style="display:inline-block;margin-bottom:1.2rem;margin-left:0.5rem;padding:0.45rem 1.1rem;background:#0f172a;color:#f1f5f9;border:1px solid #334155;border-radius:6px;text-decoration:none;font-size:0.88rem;">📄 View Source</a>'

    # Conditional label/case column
    has_labels  = any(r.get("label") for r in rows)
    status_col  = 6 if has_labels else 5
    label_th    = '<th onclick="sortTable(3)">Case</th>' if has_labels else ""
    tc_idx      = 4 if has_labels else 3
    fc_idx      = 5 if has_labels else 4
    headers_js  = '["ID","Line","Type","Case","True hits","False hits","Status"]' if has_labels else '["ID","Line","Type","True hits","False hits","Status"]'

    table_rows = ""
    for r in rows:
        if r["covered"]:
            row_class = "full"
        elif r["true_count"] > 0 or r["false_count"] > 0:
            row_class = "partial"
        else:
            row_class = "none"

        btype  = r["type"].replace("_statement", "").replace("_", "-")
        status = "FULL" if r["covered"] else ("PARTIAL" if r["true_count"] > 0 or r["false_count"] > 0 else "NONE")
        t_badge = f'<span class="badge hit">{r["true_count"]}</span>'  if r["true_count"]  > 0 else '<span class="badge miss">0</span>'
        f_badge = f'<span class="badge hit">{r["false_count"]}</span>' if r["false_count"] > 0 else '<span class="badge miss">0</span>'
        label_td = f'<td><code>{r.get("label","")}</code></td>' if has_labels else ""

        src_link = f'{source_html_name}#line-{r["line"]}' if source_html_name and r["line"] != "?" else ""
        onclick  = f'onclick="window.open(\'{src_link}\',\'_blank\')"' if src_link else ""
        cursor   = 'style="cursor:pointer"' if src_link else ""

        table_rows += (
            f'<tr class="{row_class}" data-status="{status}" {onclick} {cursor}>'
            f'<td>{r["branch_id"]}</td>'
            f'<td>{r["line"]}</td>'
            f'<td><code>{btype}</code></td>'
            f'{label_td}'
            f'<td>{t_badge}</td>'
            f'<td>{f_badge}</td>'
            f'<td><span class="status {row_class}">{status}</span></td>'
            f'</tr>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Coverage Report — {os.path.basename(source_file)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg:#f5f7fa; --surface:#ffffff; --text:#1a1a2e; --subtext:#555;
    --border:#e5e7eb; --header:#1a1a2e; --header-hover:#2d2d5e;
    --row-full:#bbf7d0; --row-partial:#fde68a; --row-none:#fecaca;
    --row-full-hover:#86efac; --row-partial-hover:#fcd34d; --row-none-hover:#fca5a5;
  }}
  [data-theme="dark"] {{
    --bg:#0f172a; --surface:#1e293b; --text:#f1f5f9; --subtext:#94a3b8;
    --border:#334155; --header:#0f172a; --header-hover:#1e3a5f;
    --row-full:#14532d; --row-partial:#78350f; --row-none:#7f1d1d;
    --row-full-hover:#166534; --row-partial-hover:#92400e; --row-none-hover:#991b1b;
  }}
  body {{ font-family:"Segoe UI",Arial,sans-serif; background:var(--bg); color:var(--text); padding:2em; transition:background 0.2s,color 0.2s; }}
  h1 {{ font-size:1.5em; margin-bottom:0.2em; }}
  .subtitle {{ color:var(--subtext); font-size:0.9em; margin-bottom:1.5em; }}
  .topbar {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5em; }}
  .dark-toggle {{ background:var(--surface); border:1px solid var(--border); color:var(--text); padding:0.4em 0.9em; border-radius:6px; cursor:pointer; font-size:0.85em; }}
  .cards {{ display:flex; gap:1em; margin-bottom:1.5em; flex-wrap:wrap; }}
  .card {{ background:var(--surface); border-radius:10px; padding:1em 1.5em; box-shadow:0 2px 8px rgba(0,0,0,0.08); min-width:150px; border:1px solid var(--border); }}
  .card .val {{ font-size:1.8em; font-weight:bold; }}
  .card .lbl {{ font-size:0.8em; color:var(--subtext); margin-top:0.2em; }}
  .bar-wrap {{ background:var(--surface); border-radius:10px; padding:1.2em 1.5em; box-shadow:0 2px 8px rgba(0,0,0,0.08); margin-bottom:1.5em; border:1px solid var(--border); }}
  .bar-label {{ display:flex; justify-content:space-between; margin-bottom:0.5em; font-size:0.9em; color:var(--subtext); }}
  .bar-bg {{ background:var(--border); border-radius:999px; height:22px; }}
  .bar-fg {{ background:{bar_color}; border-radius:999px; height:22px; width:{pct:.1f}%; }}
  .controls {{ display:flex; gap:0.8em; margin-bottom:0.6em; align-items:center; flex-wrap:wrap; }}
  .controls input  {{ padding:0.4em 0.8em; border:1px solid var(--border); border-radius:6px; font-size:0.9em; width:240px; background:var(--surface); color:var(--text); }}
  .controls select {{ padding:0.4em 0.8em; border:1px solid var(--border); border-radius:6px; font-size:0.9em; background:var(--surface); color:var(--text); }}
  .row-count {{ font-size:0.82em; color:var(--subtext); margin-bottom:0.8em; }}
  table {{ width:100%; border-collapse:collapse; background:var(--surface); border-radius:10px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08); border:1px solid var(--border); }}
  th {{ background:var(--header); color:#fff; padding:0.75em 1em; text-align:left; font-size:0.85em; cursor:pointer; user-select:none; white-space:nowrap; }}
  th:hover {{ background:var(--header-hover); }}
  th.sorted-asc::after  {{ content:" ▲"; font-size:0.75em; }}
  th.sorted-desc::after {{ content:" ▼"; font-size:0.75em; }}
  td {{ padding:0.45em 1em; font-size:0.88em; border-bottom:1px solid var(--border); }}
  tr:last-child td {{ border-bottom:none; }}
  tr.full    {{ background:var(--row-full); }}
  tr.partial {{ background:var(--row-partial); }}
  tr.none    {{ background:var(--row-none); }}
  tr.full:hover    {{ background:var(--row-full-hover); }}
  tr.partial:hover {{ background:var(--row-partial-hover); }}
  tr.none:hover    {{ background:var(--row-none-hover); }}
  .badge {{ display:inline-block; padding:0.15em 0.6em; border-radius:999px; font-size:0.82em; font-weight:bold; }}
  .badge.hit  {{ background:#16a34a; color:#fff; }}
  .badge.miss {{ background:#dc2626; color:#fff; }}
  .status {{ display:inline-block; padding:0.2em 0.7em; border-radius:6px; font-size:0.78em; font-weight:bold; }}
  .status.full    {{ background:#16a34a; color:#fff; }}
  .status.partial {{ background:#d97706; color:#fff; }}
  .status.none    {{ background:#dc2626; color:#fff; }}
  code {{ background:var(--border); padding:0.1em 0.4em; border-radius:4px; font-size:0.85em; }}
  .export-btn {{ background:#1a1a2e; color:white; border:none; padding:0.4em 1em; border-radius:6px; cursor:pointer; font-size:0.85em; margin-left:auto; }}
  .export-btn:hover {{ background:#2d2d5e; }}
</style>
</head>
<body>
{back_button}{source_btn}
<div class="topbar">
  <div>
    <h1>🔍 Coverage Report</h1>
    <p class="subtitle"><strong>File:</strong> {source_file} &nbsp;|&nbsp; <strong>Generated:</strong> {date_str}</p>
  </div>
  <button class="dark-toggle" onclick="toggleDark()">🌙 Dark mode</button>
</div>
<div class="cards">
  <div class="card"><div class="val">{len(rows)}</div><div class="lbl">Total branches</div></div>
  <div class="card"><div class="val">{total_edges}</div><div class="lbl">Total edges</div></div>
  <div class="card"><div class="val">{covered_edges}</div><div class="lbl">Covered edges</div></div>
  <div class="card"><div class="val" style="color:{bar_color}">{pct:.1f}%</div><div class="lbl">Branch coverage</div></div>
</div>
<div class="bar-wrap">
  <div class="bar-label"><span>Branch Coverage</span><span>{covered_edges}/{total_edges} edges</span></div>
  <div class="bar-bg"><div class="bar-fg"></div></div>
</div>
<div class="controls">
  <input type="text" id="search" placeholder="🔍 Search by line or type…" oninput="applyFilters()">
  <select id="filter" onchange="applyFilters()">
    <option value="all">All statuses</option>
    <option value="FULL">FULL only</option>
    <option value="PARTIAL">PARTIAL only</option>
    <option value="NONE">NONE only</option>
    <option value="uncovered">Hide fully covered</option>
  </select>
  <button class="export-btn" onclick="exportCSV()">⬇ Download CSV</button>
</div>
<div class="row-count" id="rowCount"></div>
<table id="covTable">
  <thead>
  <tr>
    <th onclick="sortTable(0)">ID</th>
    <th onclick="sortTable(1)">Line</th>
    <th onclick="sortTable(2)">Type</th>
    {label_th}
    <th onclick="sortTable({tc_idx})">True hits</th>
    <th onclick="sortTable({fc_idx})">False hits</th>
    <th onclick="sortTable({status_col})">Status</th>
  </tr>
  </thead>
  <tbody id="tableBody">
{table_rows}
  </tbody>
</table>
<script>
  let sortCol = {status_col}, sortAsc = true;
  const STATUS_ORDER = {{"NONE":0,"PARTIAL":1,"FULL":2}};
  function getStatus(row) {{ return row.getAttribute("data-status") || ""; }}
  (function defaultSort() {{
    const tbody = document.getElementById("tableBody");
    const rows  = Array.from(tbody.querySelectorAll("tr"));
    rows.sort((a,b) => (STATUS_ORDER[getStatus(a)]??9)-(STATUS_ORDER[getStatus(b)]??9));
    rows.forEach(r => tbody.appendChild(r));
    document.querySelectorAll("th")[{status_col}].classList.add("sorted-asc");
    updateCount();
  }})();
  function sortTable(col) {{
    const tbody = document.getElementById("tableBody");
    const rows  = Array.from(tbody.querySelectorAll("tr"));
    if (sortCol===col) sortAsc=!sortAsc; else {{sortCol=col;sortAsc=true;}}
    rows.sort((a,b) => {{
      if (col==={status_col}) {{
        const av=STATUS_ORDER[getStatus(a)]??9, bv=STATUS_ORDER[getStatus(b)]??9;
        return sortAsc?av-bv:bv-av;
      }}
      const av=a.cells[col].innerText.trim(), bv=b.cells[col].innerText.trim();
      const an=parseFloat(av), bn=parseFloat(bv);
      const cmp=isNaN(an)||isNaN(bn)?av.localeCompare(bv):an-bn;
      return sortAsc?cmp:-cmp;
    }});
    rows.forEach(r => tbody.appendChild(r));
    document.querySelectorAll("th").forEach((th,i) => {{
      th.classList.remove("sorted-asc","sorted-desc");
      if (i===col) th.classList.add(sortAsc?"sorted-asc":"sorted-desc");
    }});
    updateCount();
  }}
  function applyFilters() {{
    const search=document.getElementById("search").value.toLowerCase();
    const filter=document.getElementById("filter").value;
    document.querySelectorAll("#tableBody tr").forEach(row => {{
      const text=row.innerText.toLowerCase(), status=getStatus(row);
      const matchS=!search||text.includes(search);
      const matchF=filter==="all"?true:filter==="uncovered"?status!=="FULL":status===filter;
      row.style.display=matchS&&matchF?"":"none";
    }});
    updateCount();
  }}
  function updateCount() {{
    const all=document.querySelectorAll("#tableBody tr");
    const visible=Array.from(all).filter(r=>r.style.display!=="none").length;
    document.getElementById("rowCount").textContent=
      visible===all.length?`Showing all ${{all.length}} branches`:`Showing ${{visible}} of ${{all.length}} branches`;
  }}
  function toggleDark() {{
    const html=document.documentElement;
    const isDark=html.getAttribute("data-theme")==="dark";
    html.setAttribute("data-theme",isDark?"":"dark");
    document.querySelector(".dark-toggle").textContent=isDark?"🌙 Dark mode":"☀️ Light mode";
  }}
  function exportCSV() {{
    const rows=Array.from(document.querySelectorAll("#tableBody tr")).filter(r=>r.style.display!=="none");
    const headers={headers_js};
    const lines=[headers.join(",")];
    rows.forEach(row => {{
      const cells=Array.from(row.cells).map(c=>`"${{c.innerText.trim()}}"`);
      lines.push(cells.join(","));
    }});
    const blob=new Blob([lines.join("\\n")],{{type:"text/csv"}});
    const a=document.createElement("a");
    a.href=URL.createObjectURL(blob);
    a.download="coverage_export.csv";
    a.click();
  }}
</script>
</body>
</html>"""

    try:
        with open(output_path, "w") as f:
            f.write(html)
        print(f"✓ Wrote HTML to {output_path}")
    except OSError as e:
        print(f"❌ Error: could not write {output_path}: {e}")
        sys.exit(1)

    return covered_edges, total_edges, pct


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 report.py <branch_map.json> <coverage.json>")
        sys.exit(1)

    branch_map_path = sys.argv[1]
    coverage_path   = sys.argv[2]

    if not os.path.exists(branch_map_path):
        print(f"❌ Error: branch map not found: {branch_map_path}")
        sys.exit(1)

    branch_map_data  = load_branch_map(branch_map_path)
    coverage         = load_coverage(coverage_path)
    rows             = merge(branch_map_data, coverage)

    base             = branch_map_path.replace("_branch_map.json", "")
    source_file      = os.path.basename(base).replace("_inst", ".c")
    csv_out          = base + "_report.csv"
    html_out         = base + "_report.html"
    source_html_out  = base + "_source.html"
    source_html_name = os.path.basename(source_html_out)

    write_csv(rows, csv_out, source_file)

    source_ok = write_source_html(
        rows, branch_map_data, source_html_out,
        report_html_name=os.path.basename(html_out)
    )

    covered_edges, total_edges, pct = write_html(
        rows, html_out, source_file,
        source_html_name=source_html_name if source_ok else None
    )
    print(f"\n📊 Coverage: {covered_edges}/{total_edges} edges ({pct:.1f}%)")


if __name__ == "__main__":
    main()
