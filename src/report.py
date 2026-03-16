#!/usr/bin/env python3
"""
C Testing Coverage Tool - Report Generator
Reads branch_map.json + coverage.json and outputs HTML + CSV reports
"""


import sys, json, os, csv
from datetime import datetime



def load_branch_map(path):
    try:
        with open(path) as f:
            return json.load(f)["branches"]
    except FileNotFoundError:
        print(f"❌ Error: branch map not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: branch map is malformed JSON: {e}")
        sys.exit(1)
    except KeyError:
        print(f"❌ Error: branch map missing 'branches' key")
        sys.exit(1)



def load_coverage(path):
    """Returns dict: {branch_id: {"true": N, "false": N}}"""
    if not os.path.exists(path):
        print("⚠️  Warning: coverage file not found — treating all branches as uncovered")
        return {}
    with open(path) as f:
        data = json.load(f)
    branches = data.get("branches", [])
    return {int(entry["id"]): entry for entry in branches}



def merge(branch_map, coverage):
    """Merge branch metadata with hit counts"""
    rows = []
    for b in branch_map:
        bid = b["id"]
        hits = coverage.get(int(bid), {})
        true_count  = hits.get("true",  0)
        false_count = hits.get("false", 0)
        if "covered" in hits:
            covered = hits["covered"]
        else:
            covered = true_count > 0 and false_count > 0

        rows.append({
            "branch_id":    bid,
            "line":         b.get("line",  "?"),
            "type":         b.get("type",  "?"),
            "label":        b.get("label", ""),
            "true_count":   true_count,
            "false_count":  false_count,
            "covered":      covered,
        })
    return rows



def write_csv(rows, output_path, source_file):
    try:
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "file", "branch_id", "line", "type",
                "label", "true_count", "false_count", "covered",
            ])
            writer.writeheader()
            for r in rows:
                writer.writerow({"file": source_file, **r})

            total_edges   = len(rows) * 2
            covered_edges = sum(1 for r in rows if r["true_count"]  > 0) + \
                            sum(1 for r in rows if r["false_count"] > 0)
            pct = (covered_edges / total_edges * 100) if total_edges > 0 else 0
            writer.writerow({
                "file":        "SUMMARY",
                "branch_id":   "",
                "line":        "",
                "type":        "",
                "label":       f"{covered_edges}/{total_edges} edges",
                "true_count":  "",
                "false_count": "",
                "covered":     f"{pct:.1f}%",
            })
        print(f"✓ Wrote CSV to {output_path}")
    except OSError as e:
        print(f"❌ Error: could not write {output_path}: {e}")
        sys.exit(1)



def write_html(rows, output_path, source_file):
    total_edges   = len(rows) * 2
    covered_true  = sum(1 for r in rows if r["true_count"]  > 0)
    covered_false = sum(1 for r in rows if r["false_count"] > 0)
    covered_edges = covered_true + covered_false
    pct      = (covered_edges / total_edges * 100) if total_edges > 0 else 0
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if pct >= 80:
        bar_color = "#16a34a"
    elif pct >= 50:
        bar_color = "#d97706"
    else:
        bar_color = "#dc2626"

    # Always show back button — summary_report.html is in the same dir
    back_button = '<a href="summary_report.html" style="display:inline-block;margin-bottom:1.2rem;padding:0.45rem 1.1rem;background:#1a1a2e;color:#fff;border-radius:6px;text-decoration:none;font-size:0.88rem;font-weight:500;">← Back to Summary</a>'

    table_rows = ""
    for r in rows:
        if r["covered"]:
            row_class = "full"
        elif r["true_count"] > 0 or r["false_count"] > 0:
            row_class = "partial"
        else:
            row_class = "none"
        label   = r["label"] or "-"
        btype   = r["type"].replace("_statement", "").replace("_", "-")
        status  = (
            "FULL" if r["covered"]
            else ("PARTIAL" if r["true_count"] > 0 or r["false_count"] > 0 else "NONE")
        )
        t_badge = (
            f'<span class="badge hit">{r["true_count"]}</span>'
            if r["true_count"] > 0 else '<span class="badge miss">0</span>'
        )
        f_badge = (
            f'<span class="badge hit">{r["false_count"]}</span>'
            if r["false_count"] > 0 else '<span class="badge miss">0</span>'
        )
        table_rows += (
            f'<tr class="{row_class}" data-status="{status}">'
            f'<td>{r["branch_id"]}</td>'
            f'<td>{r["line"]}</td>'
            f'<td><code>{btype}</code></td>'
            f'<td>{label}</td>'
            f'<td>{t_badge}</td>'
            f'<td>{f_badge}</td>'
            f'<td><span class="status {row_class}">{status}</span></td>'
            f'</tr>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Coverage Report — {os.path.basename(source_file)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg:       #f5f7fa;
    --surface:  #ffffff;
    --text:     #1a1a2e;
    --subtext:  #555;
    --border:   #e5e7eb;
    --header:   #1a1a2e;
    --header-hover: #2d2d5e;
    --row-full:    #bbf7d0;
    --row-partial: #fde68a;
    --row-none:    #fecaca;
    --row-full-hover:    #86efac;
    --row-partial-hover: #fcd34d;
    --row-none-hover:    #fca5a5;
  }}

  [data-theme="dark"] {{
    --bg:       #0f172a;
    --surface:  #1e293b;
    --text:     #f1f5f9;
    --subtext:  #94a3b8;
    --border:   #334155;
    --header:   #0f172a;
    --header-hover: #1e3a5f;
    --row-full:    #14532d;
    --row-partial: #78350f;
    --row-none:    #7f1d1d;
    --row-full-hover:    #166534;
    --row-partial-hover: #92400e;
    --row-none-hover:    #991b1b;
  }}

  body {{ font-family: "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--text); padding: 2em; transition: background 0.2s, color 0.2s; }}
  h1 {{ font-size: 1.5em; margin-bottom: 0.2em; }}
  .subtitle {{ color: var(--subtext); font-size: 0.9em; margin-bottom: 1.5em; }}

  .topbar {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5em; }}
  .dark-toggle {{ background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 0.4em 0.9em; border-radius: 6px; cursor: pointer; font-size: 0.85em; }}
  .dark-toggle:hover {{ background: var(--border); }}

  .cards {{ display: flex; gap: 1em; margin-bottom: 1.5em; flex-wrap: wrap; }}
  .card {{ background: var(--surface); border-radius: 10px; padding: 1em 1.5em; box-shadow: 0 2px 8px rgba(0,0,0,0.08); min-width: 150px; border: 1px solid var(--border); }}
  .card .val {{ font-size: 1.8em; font-weight: bold; }}
  .card .lbl {{ font-size: 0.8em; color: var(--subtext); margin-top: 0.2em; }}

  .bar-wrap {{ background: var(--surface); border-radius: 10px; padding: 1.2em 1.5em; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 1.5em; border: 1px solid var(--border); }}
  .bar-label {{ display: flex; justify-content: space-between; margin-bottom: 0.5em; font-size: 0.9em; color: var(--subtext); }}
  .bar-bg {{ background: var(--border); border-radius: 999px; height: 22px; width: 100%; }}
  .bar-fg {{ background: {bar_color}; border-radius: 999px; height: 22px; width: {pct:.1f}%; }}

  .controls {{ display: flex; gap: 0.8em; margin-bottom: 0.6em; align-items: center; flex-wrap: wrap; }}
  .controls input  {{ padding: 0.4em 0.8em; border: 1px solid var(--border); border-radius: 6px; font-size: 0.9em; width: 240px; background: var(--surface); color: var(--text); }}
  .controls select {{ padding: 0.4em 0.8em; border: 1px solid var(--border); border-radius: 6px; font-size: 0.9em; background: var(--surface); color: var(--text); }}
  .row-count {{ font-size: 0.82em; color: var(--subtext); margin-bottom: 0.8em; }}

  table {{ width: 100%; border-collapse: collapse; background: var(--surface); border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid var(--border); }}
  th {{ background: var(--header); color: #fff; padding: 0.75em 1em; text-align: left; font-size: 0.85em; cursor: pointer; user-select: none; white-space: nowrap; }}
  th:hover {{ background: var(--header-hover); }}
  th.sorted-asc::after  {{ content: " ▲"; font-size: 0.75em; }}
  th.sorted-desc::after {{ content: " ▼"; font-size: 0.75em; }}
  td {{ padding: 0.65em 1em; font-size: 0.88em; border-bottom: 1px solid var(--border); }}
  tr:last-child td {{ border-bottom: none; }}

  tr.full    {{ background: var(--row-full); }}
  tr.partial {{ background: var(--row-partial); }}
  tr.none    {{ background: var(--row-none); }}
  tr.full:hover    {{ background: var(--row-full-hover); }}
  tr.partial:hover {{ background: var(--row-partial-hover); }}
  tr.none:hover    {{ background: var(--row-none-hover); }}

  .badge {{ display: inline-block; padding: 0.15em 0.6em; border-radius: 999px; font-size: 0.82em; font-weight: bold; }}
  .badge.hit  {{ background: #16a34a; color: #fff; }}
  .badge.miss {{ background: #dc2626; color: #fff; }}

  .status {{ display: inline-block; padding: 0.2em 0.7em; border-radius: 6px; font-size: 0.78em; font-weight: bold; letter-spacing: 0.04em; }}
  .status.full    {{ background: #16a34a; color: #fff; }}
  .status.partial {{ background: #d97706; color: #fff; }}
  .status.none    {{ background: #dc2626; color: #fff; }}

  code {{ background: var(--border); padding: 0.1em 0.4em; border-radius: 4px; font-size: 0.85em; }}

  .export-btn {{ background: #1a1a2e; color: white; border: none; padding: 0.4em 1em; border-radius: 6px; cursor: pointer; font-size: 0.85em; margin-left: auto; }}
  .export-btn:hover {{ background: #2d2d5e; }}
</style>
</head>
<body>
{back_button}
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
  <input type="text" id="search" placeholder="🔍 Search by line, type, label…" oninput="applyFilters()">
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
    <th onclick="sortTable(3)">Label</th>
    <th onclick="sortTable(4)">True hits</th>
    <th onclick="sortTable(5)">False hits</th>
    <th onclick="sortTable(6)">Status</th>
  </tr>
  </thead>
  <tbody id="tableBody">
{table_rows}  </tbody>
</table>

<script>
  let sortCol = 6, sortAsc = true;
  const STATUS_ORDER = {{"NONE": 0, "PARTIAL": 1, "FULL": 2}};

  function getStatus(row) {{
    return row.getAttribute("data-status") || "";
  }}

  (function defaultSort() {{
    const tbody = document.getElementById("tableBody");
    const rows  = Array.from(tbody.querySelectorAll("tr"));
    rows.sort((a, b) => (STATUS_ORDER[getStatus(a)] ?? 9) - (STATUS_ORDER[getStatus(b)] ?? 9));
    rows.forEach(r => tbody.appendChild(r));
    document.querySelectorAll("th")[6].classList.add("sorted-asc");
    updateCount();
  }})();

  function sortTable(col) {{
    const tbody = document.getElementById("tableBody");
    const rows  = Array.from(tbody.querySelectorAll("tr"));
    if (sortCol === col) sortAsc = !sortAsc; else {{ sortCol = col; sortAsc = true; }}
    rows.sort((a, b) => {{
      let av, bv;
      if (col === 6) {{
        av = STATUS_ORDER[getStatus(a)] ?? 9;
        bv = STATUS_ORDER[getStatus(b)] ?? 9;
        return sortAsc ? av - bv : bv - av;
      }}
      av = a.cells[col].innerText.trim();
      bv = b.cells[col].innerText.trim();
      const an = parseFloat(av), bn = parseFloat(bv);
      const cmp = isNaN(an) || isNaN(bn) ? av.localeCompare(bv) : an - bn;
      return sortAsc ? cmp : -cmp;
    }});
    rows.forEach(r => tbody.appendChild(r));
    document.querySelectorAll("th").forEach((th, i) => {{
      th.classList.remove("sorted-asc", "sorted-desc");
      if (i === col) th.classList.add(sortAsc ? "sorted-asc" : "sorted-desc");
    }});
    updateCount();
  }}

  function applyFilters() {{
    const search = document.getElementById("search").value.toLowerCase();
    const filter = document.getElementById("filter").value;
    document.querySelectorAll("#tableBody tr").forEach(row => {{
      const text    = row.innerText.toLowerCase();
      const status  = getStatus(row);
      const matchS  = !search || text.includes(search);
      const matchF  = filter === "all"        ? true
                    : filter === "uncovered"  ? status !== "FULL"
                    : status === filter;
      row.style.display = matchS && matchF ? "" : "none";
    }});
    updateCount();
  }}

  function updateCount() {{
    const all     = document.querySelectorAll("#tableBody tr");
    const visible = Array.from(all).filter(r => r.style.display !== "none").length;
    document.getElementById("rowCount").textContent =
      visible === all.length ? `Showing all ${{all.length}} branches`
                             : `Showing ${{visible}} of ${{all.length}} branches`;
  }}

  function toggleDark() {{
    const html = document.documentElement;
    const isDark = html.getAttribute("data-theme") === "dark";
    html.setAttribute("data-theme", isDark ? "" : "dark");
    document.querySelector(".dark-toggle").textContent = isDark ? "🌙 Dark mode" : "☀️ Light mode";
  }}

  function exportCSV() {{
    const rows = Array.from(document.querySelectorAll("#tableBody tr"))
      .filter(r => r.style.display !== "none");
    const headers = ["ID","Line","Type","Label","True hits","False hits","Status"];
    const lines = [headers.join(",")];
    rows.forEach(row => {{
      const cells = Array.from(row.cells).map(c => `"${{c.innerText.trim()}}"`);
      lines.push(cells.join(","));
    }});
    const blob = new Blob([lines.join("\\n")], {{type: "text/csv"}});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "coverage_export.csv";
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

    branch_map = load_branch_map(branch_map_path)
    coverage   = load_coverage(coverage_path)
    rows       = merge(branch_map, coverage)

    base        = branch_map_path.replace("_branch_map.json", "")
    source_file = os.path.basename(base).replace("_inst", ".c")
    csv_out     = base + "_report.csv"
    html_out    = base + "_report.html"

    write_csv(rows, csv_out, source_file)
    covered_edges, total_edges, pct = write_html(rows, html_out, source_file)
    print(f"\n📊 Coverage: {covered_edges}/{total_edges} edges ({pct:.1f}%)")



if __name__ == "__main__":
    main()
