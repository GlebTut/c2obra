#!/usr/bin/env python3
"""
C²oBra - Summary Report Generator
Reads all *_branch_map.json + *_coverage.json in a directory and outputs:
  - summary_report.html  (overall stats + per-file breakdown with links)
"""

import sys, json, os
from datetime import datetime


def load_branch_map(path):
    try:
        with open(path) as f:
            return json.load(f)["branches"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        print(f"\u26a0\ufe0f  Skipping {path}: {e}")
        return []


def load_coverage(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return {int(e["id"]): e for e in data.get("branches", [])}
    except (json.JSONDecodeError, KeyError):
        return {}


def compute_stats(branch_map, coverage):
    total_edges   = len(branch_map) * 2
    covered_edges = 0
    for b in branch_map:
        hits = coverage.get(int(b["id"]), {})
        if hits.get("true",  0) > 0:
            covered_edges += 1
        if hits.get("false", 0) > 0:
            covered_edges += 1
    pct = (covered_edges / total_edges * 100) if total_edges > 0 else 0.0
    return total_edges, covered_edges, pct


def collect_file_stats(directory):
    files = []
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith("_branch_map.json"):
            continue

        map_path  = os.path.join(directory, fname)
        base      = fname.replace("_branch_map.json", "")
        cov_path  = os.path.join(directory, base + "_coverage.json")

        html_path   = os.path.basename(base + "_report.html")
        source_html = os.path.basename(base + "_source.html")
        source_html_exists = os.path.exists(os.path.join(directory, source_html))

        branch_map = load_branch_map(map_path)
        coverage   = load_coverage(cov_path)
        total_edges, covered_edges, pct = compute_stats(branch_map, coverage)

        files.append({
            "name":          base.replace("_inst", ".c"),
            "html":          html_path,
            "source_html":   source_html if source_html_exists else None,
            "total_edges":   total_edges,
            "covered_edges": covered_edges,
            "pct":           pct,
        })
    return files


def write_summary_html(files, output_path):
    total_edges   = sum(f["total_edges"]   for f in files)
    covered_edges = sum(f["covered_edges"] for f in files)
    overall_pct   = (covered_edges / total_edges * 100) if total_edges > 0 else 0.0
    date_str      = datetime.now().strftime("%Y-%m-%d %H:%M")

    bar_color = "#16a34a" if overall_pct >= 80 else "#d97706" if overall_pct >= 50 else "#dc2626"

    table_rows = ""
    for f in files:
        fc      = "#16a34a" if f["pct"] >= 80 else "#d97706" if f["pct"] >= 50 else "#dc2626"
        bar_w   = f"{f['pct']:.1f}"
        row_cls = "full" if f["pct"] >= 80 else ("partial" if f["pct"] >= 50 else "none")
        source_cell = (
            f'<td><a href="{f["source_html"]}" style="color:#60a5fa;font-size:1.1em" title="View source">\U0001f4c4</a></td>'
            if f["source_html"]
            else '<td style="color:var(--subtext)">\u2014</td>'
        )
        table_rows += (
            f'<tr class="{row_cls}">'
            f'<td><a href="{f["html"]}" style="color:#60a5fa;font-weight:500">{f["name"]}</a></td>'
            f'<td>{f["total_edges"]}</td>'
            f'<td>{f["covered_edges"]}</td>'
            f'<td><div style="background:var(--border);border-radius:999px;height:10px;width:120px">'
            f'<div style="background:{fc};border-radius:999px;height:10px;width:{bar_w}%"></div></div></td>'
            f'<td style="color:{fc};font-weight:bold">{f["pct"]:.1f}%</td>'
            f'{source_cell}'
            f'</tr>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>C\u00b2oBra \u2014 Coverage Summary</title>
<script>
  (function(){{
    const t = (function(){{try{{return localStorage.getItem("theme")}}catch(e){{return null}}}}()) || "dark";
    document.documentElement.setAttribute("data-theme", t);
  }})();
</script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg:#0f172a; --surface:#1e293b; --text:#f1f5f9; --subtext:#94a3b8;
    --border:#334155; --header:#0f172a; --header-hover:#1e3a5f;
    --row-full:#0f3320;    --row-full-hover:#134a2c;
    --row-partial:#4a2500; --row-partial-hover:#5e3000;
    --row-none:#4a0a0a;    --row-none-hover:#600e0e;
  }}
  [data-theme="light"] {{
    --bg:#f5f7fa; --surface:#ffffff; --text:#1a1a2e; --subtext:#555;
    --border:#e5e7eb; --header:#1a1a2e; --header-hover:#2d2d5e;
    --row-full:#bbf7d0;    --row-full-hover:#86efac;
    --row-partial:#fde68a; --row-partial-hover:#fcd34d;
    --row-none:#fecaca;    --row-none-hover:#fca5a5;
  }}
  body {{ font-family:"Segoe UI",Arial,sans-serif; background:var(--bg); color:var(--text); transition:background 0.2s,color 0.2s; min-height:100vh; }}
  .topbar {{
    display:flex; justify-content:space-between; align-items:center;
    padding:0.7rem 2rem; background:var(--header);
    border-bottom:2px solid var(--border);
    position:sticky; top:0; z-index:100;
  }}
  .topbar-left {{ display:flex; align-items:center; gap:1rem; }}
  .topbar-right {{ display:flex; align-items:center; gap:0.6rem; }}
  .toggle-btn {{
    background:rgba(96,165,250,0.12); border:1px solid rgba(96,165,250,0.3);
    color:var(--subtext); padding:0.38em 0.9em; border-radius:7px;
    cursor:pointer; font-size:0.84rem; transition:background 0.15s;
  }}
  .toggle-btn:hover {{ background:rgba(96,165,250,0.25); }}
  .page {{ max-width:1100px; margin:0 auto; padding:1.6rem 2rem 3rem; }}
  .file-meta {{ font-size:0.82rem; color:var(--subtext); margin-bottom:1.6rem; display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; }}
  .file-meta strong {{ color:var(--text); }}
  .cards {{ display:flex; gap:1rem; margin-bottom:1.4rem; flex-wrap:wrap; }}
  .card {{
    background:var(--surface); border:1px solid var(--border);
    border-top:3px solid {bar_color};
    border-radius:10px; padding:1rem 1.4rem;
    box-shadow:0 2px 12px rgba(0,0,0,0.25); min-width:140px; flex:1;
  }}
  .card .val {{ font-size:2rem; font-weight:800; line-height:1; letter-spacing:-0.5px; }}
  .card .lbl {{ font-size:0.78rem; color:var(--subtext); margin-top:0.35rem; font-weight:500; text-transform:uppercase; letter-spacing:0.04em; }}
  .bar-wrap {{
    background:var(--surface); border:1px solid var(--border);
    border-radius:10px; padding:1.1rem 1.4rem;
    box-shadow:0 2px 12px rgba(0,0,0,0.2); margin-bottom:1.6rem;
  }}
  .bar-label {{ display:flex; justify-content:space-between; margin-bottom:0.6rem; font-size:0.88rem; color:var(--subtext); }}
  .bar-label strong {{ color:var(--text); }}
  .bar-bg {{ background:var(--border); border-radius:999px; height:20px; overflow:hidden; }}
  .bar-fg {{
    background:linear-gradient(90deg,{bar_color},{bar_color}cc);
    border-radius:999px; height:20px; width:{overall_pct:.1f}%;
    transition:width 0.8s cubic-bezier(.4,0,.2,1);
  }}
  .section-heading {{
    font-size:0.82rem; font-weight:700; color:#569cd6;
    text-transform:uppercase; letter-spacing:0.1em;
    margin:1.8rem 0 0.9rem; display:flex; align-items:center; gap:0.6rem;
  }}
  .section-heading::before {{
    content:\'\'; display:inline-block; width:3px; height:1em;
    background:#569cd6; border-radius:2px; flex-shrink:0;
  }}
  .controls {{ display:flex; gap:0.7rem; margin-bottom:0.6rem; align-items:center; flex-wrap:wrap; }}
  .controls input {{
    padding:0.42em 0.8em; border:1px solid var(--border);
    border-radius:7px; font-size:0.88rem; width:260px;
    background:var(--surface); color:var(--text); transition:border-color 0.15s;
  }}
  .controls input:focus {{ outline:none; border-color:#569cd6; }}
  .row-count {{ font-size:0.8rem; color:var(--subtext); margin-bottom:0.7rem; }}
  .table-wrap {{ overflow-x:auto; border-radius:10px; border:1px solid var(--border); box-shadow:0 2px 12px rgba(0,0,0,0.2); }}
  table {{ width:100%; border-collapse:collapse; background:var(--surface); }}
  th {{
    background:var(--header); color:#fff;
    padding:0.7em 1em; text-align:left; font-size:0.84rem; font-weight:600;
    cursor:pointer; user-select:none; white-space:nowrap;
    border-bottom:2px solid var(--border);
  }}
  th:hover {{ background:var(--header-hover); }}
  th.sorted-asc::after  {{ content:" \u25b2"; font-size:0.7em; }}
  th.sorted-desc::after {{ content:" \u25bc"; font-size:0.7em; }}
  td {{ padding:0.52em 1em; font-size:0.93rem; border-bottom:1px solid var(--border); }}
  tr:last-child td {{ border-bottom:none; }}
  tr.full    {{ background:var(--row-full); }}
  tr.partial {{ background:var(--row-partial); }}
  tr.none    {{ background:var(--row-none); }}
  tr.full:hover    {{ background:var(--row-full-hover); }}
  tr.partial:hover {{ background:var(--row-partial-hover); }}
  tr.none:hover    {{ background:var(--row-none-hover); }}
  a {{ color:#60a5fa; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-left">
    <span style="font-size:1rem;font-weight:800;color:#569cd6;letter-spacing:-0.5px">
      C<sup style="font-size:0.6em;vertical-align:super">2</sup><span style="color:var(--text)">oBra</span>
    </span>
  </div>
  <div class="topbar-right">
    <button class="toggle-btn" id="themeBtn" onclick="toggleTheme()">&#9728;&#65039; Light</button>
  </div>
</div>
<div class="page">
<div class="file-meta">
  <strong>Summary Report</strong>
  <span style="opacity:0.4">&nbsp;|&nbsp;</span>
  {os.path.basename(os.path.dirname(output_path))}
  <span style="opacity:0.4">&nbsp;|&nbsp;</span>
  Generated: {date_str}
</div>
<div class="cards">
  <div class="card"><div class="val">{len(files)}</div><div class="lbl">Files analysed</div></div>
  <div class="card"><div class="val">{total_edges}</div><div class="lbl">Total branches</div></div>
  <div class="card"><div class="val">{covered_edges}</div><div class="lbl">Covered branches</div></div>
  <div class="card"><div class="val" style="color:{bar_color}">{overall_pct:.1f}%</div><div class="lbl">Overall coverage</div></div>
</div>
<div class="bar-wrap">
  <div class="bar-label">
    <span><strong>Overall Branch Coverage</strong></span>
    <span>{covered_edges}/{total_edges} branches &nbsp;&mdash;&nbsp; <strong style="color:{bar_color}">{overall_pct:.1f}%</strong></span>
  </div>
  <div class="bar-bg"><div class="bar-fg"></div></div>
</div>
<div class="section-heading">Files</div>
<div class="controls">
  <input type="text" id="search" placeholder="&#128269; Search by filename&#8230;" oninput="applySearch()">
</div>
<div class="row-count" id="rowCount"></div>
<div class="table-wrap">
  <table id="covTable">
    <thead><tr>
      <th onclick="sortTable(0)">File</th>
      <th onclick="sortTable(1)">Total branches</th>
      <th onclick="sortTable(2)">Covered branches</th>
      <th>Bar</th>
      <th onclick="sortTable(4)">Coverage %</th>
      <th>Source</th>
    </tr></thead>
    <tbody id="tableBody">
{table_rows}
    </tbody>
  </table>
</div>
</div>
<script>
  (function(){{
    const t = (function(){{try{{return localStorage.getItem("theme")}}catch(e){{return null}}}}()) || "dark";
    document.getElementById("themeBtn").textContent = t === "dark" ? "\u2600\ufe0f Light" : "\U0001f319 Dark";
  }})();
  function toggleTheme() {{
    const curr = document.documentElement.getAttribute("data-theme") || "dark";
    const next = curr === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try{{ localStorage.setItem("theme", next); }}catch(e){{}}
    document.getElementById("themeBtn").textContent = next === "dark" ? "\u2600\ufe0f Light" : "\U0001f319 Dark";
  }}
  let sortCol = 4, sortAsc = false;
  (function(){{
    sortByCol(4, false);
    document.querySelectorAll("th")[4].classList.add("sorted-desc");
    updateCount();
  }})();
  function sortByCol(col, asc) {{
    const tbody = document.getElementById("tableBody");
    const rows  = Array.from(tbody.querySelectorAll("tr"));
    rows.sort((a, b) => {{
      const av = a.cells[col].innerText.trim(), bv = b.cells[col].innerText.trim();
      const an = parseFloat(av), bn = parseFloat(bv);
      const cmp = isNaN(an)||isNaN(bn) ? av.localeCompare(bv) : an-bn;
      return asc ? cmp : -cmp;
    }});
    rows.forEach(r => tbody.appendChild(r));
  }}
  function sortTable(col) {{
    if (sortCol===col) sortAsc=!sortAsc; else {{sortCol=col; sortAsc=true;}}
    sortByCol(col, sortAsc);
    document.querySelectorAll("th").forEach((th,i) => {{
      th.classList.remove("sorted-asc","sorted-desc");
      if (i===col) th.classList.add(sortAsc?"sorted-asc":"sorted-desc");
    }});
    updateCount();
  }}
  function applySearch() {{
    const q = document.getElementById("search").value.toLowerCase();
    const rows = document.querySelectorAll("#tableBody tr");
    let visible = 0;
    rows.forEach(r => {{
      const show = !q || r.innerText.toLowerCase().includes(q);
      r.style.display = show ? "" : "none";
      if (show) visible++;
    }});
    updateCount(visible);
  }}
  function updateCount(n) {{
    const total = document.querySelectorAll("#tableBody tr").length;
    const shown = n !== undefined ? n : total;
    document.getElementById("rowCount").textContent =
      shown === total ? `Showing all ${{total}} files` : `Showing ${{shown}} of ${{total}} files`;
  }}
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"\u2713 Wrote summary report to {output_path}")
    return overall_pct, covered_edges, total_edges


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 merge_reports.py <output_directory/>")
        sys.exit(1)

    directory = sys.argv[1].rstrip("/")
    if not os.path.isdir(directory):
        print(f"\u274c Error: \'{directory}\' is not a directory")
        sys.exit(1)

    files = collect_file_stats(directory)
    if not files:
        print(f"\u26a0\ufe0f  No branch map files found in \'{directory}\'")
        sys.exit(1)

    output_path = os.path.join(directory, "summary_report.html")
    overall_pct, covered_edges, total_edges = write_summary_html(files, output_path)
    print(f"\n\U0001f4ca Overall coverage: {covered_edges}/{total_edges} branches ({overall_pct:.1f}%) across {len(files)} file(s)")


if __name__ == "__main__":
    main()
