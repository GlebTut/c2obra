#!/usr/bin/env python3
"""
C Testing Coverage Tool - Summary Report Generator
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
        print(f"⚠️  Skipping {path}: {e}")
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
    total_edges   = sum(f["total_edges"] for f in files)
    covered_edges = sum(f["covered_edges"] for f in files)
    overall_pct   = (covered_edges / total_edges * 100) if total_edges > 0 else 0.0
    date_str      = datetime.now().strftime("%Y-%m-%d %H:%M")

    bar_color = "#16a34a" if overall_pct >= 80 else "#d97706" if overall_pct >= 50 else "#dc2626"

    table_rows = ""
    for f in files:
        fc    = "#16a34a" if f["pct"] >= 80 else "#d97706" if f["pct"] >= 50 else "#dc2626"
        bar_w = f"{f['pct']:.1f}"
        source_cell = (
            f'<td><a href="{f["source_html"]}" title="View source">📄</a></td>'
            if f["source_html"]
            else '<td style="color:var(--subtext)">—</td>'
        )
        table_rows += (
            f'<tr>'
            f'<td><a href="{f["html"]}">{f["name"]}</a></td>'
            f'<td>{f["total_edges"]}</td>'
            f'<td>{f["covered_edges"]}</td>'
            f'<td><div class="mini-bar-bg"><div class="mini-bar-fg" style="width:{bar_w}%;background:{fc}"></div></div></td>'
            f'<td style="color:{fc};font-weight:bold">{f["pct"]:.1f}%</td>'
            f'{source_cell}'
            f'</tr>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Coverage Summary Report</title>
<script>
  (function(){{
    const t = (function(){{ try {{ return localStorage.getItem("theme"); }} catch(e) {{ return null; }} }})() || "dark";
    document.documentElement.setAttribute("data-theme", t);
  }})();
</script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg:#0f172a; --surface:#1e293b; --text:#f1f5f9; --subtext:#94a3b8;
    --border:#334155; --header:#0f172a; --header-hover:#1e3a5f;
  }}
  [data-theme="light"] {{
    --bg:#f5f7fa; --surface:#ffffff; --text:#1a1a2e; --subtext:#555;
    --border:#e5e7eb; --header:#1a1a2e; --header-hover:#2d2d5e;
  }}
  body {{ font-family: "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--text); padding: 2em; transition: background 0.2s, color 0.2s; }}
  h1 {{ font-size: 1.5em; margin-bottom: 0.2em; }}
  .subtitle {{ color: var(--subtext); font-size: 0.9em; margin-bottom: 1.5em; }}
  .topbar {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5em; }}
  .toggle-btn {{ background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 0.4em 0.9em; border-radius: 6px; cursor: pointer; font-size: 0.85em; }}
  .toggle-btn:hover {{ background: var(--border); }}
  .cards {{ display: flex; gap: 1em; margin-bottom: 1.5em; flex-wrap: wrap; }}
  .card {{ background: var(--surface); border-radius: 10px; padding: 1em 1.5em; box-shadow: 0 2px 8px rgba(0,0,0,0.2); min-width: 150px; border: 1px solid var(--border); }}
  .card .val {{ font-size: 1.8em; font-weight: bold; }}
  .card .lbl {{ font-size: 0.8em; color: var(--subtext); margin-top: 0.2em; }}
  .bar-wrap {{ background: var(--surface); border-radius: 10px; padding: 1.2em 1.5em; box-shadow: 0 2px 8px rgba(0,0,0,0.2); margin-bottom: 1.5em; border: 1px solid var(--border); }}
  .bar-label {{ display: flex; justify-content: space-between; margin-bottom: 0.5em; font-size: 0.9em; color: var(--subtext); }}
  .bar-bg {{ background: var(--border); border-radius: 999px; height: 22px; width: 100%; }}
  .bar-fg {{ background: {bar_color}; border-radius: 999px; height: 22px; width: {overall_pct:.1f}%; }}
  .controls {{ display: flex; gap: 0.8em; margin-bottom: 0.6em; align-items: center; flex-wrap: wrap; }}
  .controls input {{ padding: 0.4em 0.8em; border: 1px solid var(--border); border-radius: 6px; font-size: 0.9em; width: 260px; background: var(--surface); color: var(--text); }}
  .row-count {{ font-size: 0.82em; color: var(--subtext); margin-bottom: 0.8em; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--surface); border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.2); border: 1px solid var(--border); }}
  th {{ background: var(--header); color: #fff; padding: 0.75em 1em; text-align: left; font-size: 0.92em; cursor: pointer; user-select: none; white-space: nowrap; }}
  th:hover {{ background: var(--header-hover); }}
  th.sorted-asc::after {{ content: " ▲"; font-size: 0.75em; }}
  th.sorted-desc::after {{ content: " ▼"; font-size: 0.75em; }}
  td {{ padding: 0.55em 1em; font-size: 0.95em; border-bottom: 1px solid var(--border); }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: var(--border); }}
  a {{ color: #60a5fa; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .mini-bar-bg {{ background: var(--border); border-radius: 999px; height: 10px; width: 120px; }}
  .mini-bar-fg {{ border-radius: 999px; height: 10px; }}
</style>
</head>
<body>
<div class="topbar">
  <div>
    <h1>📊 Coverage Summary Report</h1>
    <p class="subtitle"><strong>Directory:</strong> {os.path.basename(os.path.dirname(output_path))} &nbsp;|&nbsp; <strong>Generated:</strong> {date_str}</p>
  </div>
  <button class="toggle-btn" id="themeBtn" onclick="toggleTheme()">☀️ Light</button>
</div>

<div class="cards">
  <div class="card"><div class="val">{len(files)}</div><div class="lbl">Files</div></div>
  <div class="card"><div class="val">{total_edges}</div><div class="lbl">Total branches</div></div>
  <div class="card"><div class="val">{covered_edges}</div><div class="lbl">Covered branches</div></div>
  <div class="card"><div class="val" style="color:{bar_color}">{overall_pct:.1f}%</div><div class="lbl">Overall coverage</div></div>
</div>

<div class="bar-wrap">
  <div class="bar-label"><span>Overall Branch Coverage</span><span>{covered_edges}/{total_edges} branches</span></div>
  <div class="bar-bg"><div class="bar-fg"></div></div>
</div>

<div class="controls">
  <input type="text" id="search" placeholder="🔍 Search by filename…" oninput="applySearch()">
</div>
<div class="row-count" id="rowCount"></div>

<table id="covTable">
  <thead>
  <tr>
    <th onclick="sortTable(0)">File</th>
    <th onclick="sortTable(1)">Total branches</th>
    <th onclick="sortTable(2)">Covered branches</th>
    <th onclick="sortTable(3)">Bar</th>
    <th onclick="sortTable(4)">Coverage %</th>
    <th>Source</th>
  </tr>
  </thead>
  <tbody id="tableBody">
{table_rows}
  </tbody>
</table>

<script>
  (function(){{
    const t = (function(){{ try {{ return localStorage.getItem("theme"); }} catch(e) {{ return null; }} }})() || "dark";
    document.getElementById("themeBtn").textContent = t === "dark" ? "☀️ Light" : "🌙 Dark";
  }})();
  function toggleTheme() {{
    const curr = document.documentElement.getAttribute("data-theme") || "dark";
    const next = curr === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {{ localStorage.setItem("theme", next); }} catch(e) {{}}
    document.getElementById("themeBtn").textContent = next === "dark" ? "☀️ Light" : "🌙 Dark";
  }}
  let sortCol = 4, sortAsc = false;
  (function defaultSort() {{
    sortByCol(4, false);
    document.querySelectorAll("th")[4].classList.add("sorted-desc");
    updateCount();
  }})();
  function sortByCol(col, asc) {{
    const tbody = document.getElementById("tableBody");
    const rows  = Array.from(tbody.querySelectorAll("tr"));
    rows.sort((a, b) => {{
      const av = a.cells[col].innerText.trim();
      const bv = b.cells[col].innerText.trim();
      const an = parseFloat(av), bn = parseFloat(bv);
      const cmp = isNaN(an) || isNaN(bn) ? av.localeCompare(bv) : an - bn;
      return asc ? cmp : -cmp;
    }});
    rows.forEach(r => tbody.appendChild(r));
  }}
  function sortTable(col) {{
    if (sortCol === col) sortAsc = !sortAsc; else {{ sortCol = col; sortAsc = true; }}
    sortByCol(col, sortAsc);
    document.querySelectorAll("th").forEach((th, i) => {{
      th.classList.remove("sorted-asc", "sorted-desc");
      if (i === col) th.classList.add(sortAsc ? "sorted-asc" : "sorted-desc");
    }});
    updateCount();
  }}
  function applySearch() {{
    const q = document.getElementById("search").value.toLowerCase();
    document.querySelectorAll("#tableBody tr").forEach(row => {{
      row.style.display = !q || row.innerText.toLowerCase().includes(q) ? "" : "none";
    }});
    updateCount();
  }}
  function updateCount() {{
    const all     = document.querySelectorAll("#tableBody tr");
    const visible = Array.from(all).filter(r => r.style.display !== "none").length;
    document.getElementById("rowCount").textContent =
      visible === all.length ? `Showing all ${{all.length}} files`
                             : `Showing ${{visible}} of ${{all.length}} files`;
  }}
</script>
</body>
</html>"""

    try:
        with open(output_path, "w") as f:
            f.write(html)
        print(f"✓ Wrote summary report to {output_path}")
    except OSError as e:
        print(f"❌ Error writing {output_path}: {e}")
        sys.exit(1)

    return overall_pct, covered_edges, total_edges


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 merge_reports.py <output_directory/>")
        sys.exit(1)

    directory = sys.argv[1].rstrip("/")
    if not os.path.isdir(directory):
        print(f"❌ Error: '{directory}' is not a directory")
        sys.exit(1)

    files = collect_file_stats(directory)
    if not files:
        print(f"⚠️  No branch map files found in '{directory}'")
        sys.exit(1)

    output_path = os.path.join(directory, "summary_report.html")
    overall_pct, covered_edges, total_edges = write_summary_html(files, output_path)
    print(f"\n📊 Overall coverage: {covered_edges}/{total_edges} branches ({overall_pct:.1f}%) across {len(files)} file(s)")


if __name__ == "__main__":
    main()
