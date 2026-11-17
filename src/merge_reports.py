#!/usr/bin/env python3
"""
C²oBra - Summary Report Generator
Reads all *_branch_map.json + *_coverage.json in a directory and outputs:
  - summary_report.html  (overall stats + per-file breakdown with links)
"""

import sys, json, os
from datetime import datetime
import edges as E


def load_branch_map(path):
    """The whole map ({"branches": [...], "edges": [...]}); {} if it cannot be read."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"\u26a0\ufe0f  Skipping {path}: {e}")
        return {}


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
    """(total edges, covered edges, pct) for one file, via edges.edge_coverage()."""
    covered_edges, total_edges = E.edge_coverage(branch_map, coverage) if branch_map else (0, 0)
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
        try:
            total_edges, covered_edges, pct = compute_stats(branch_map, coverage)
        except E.MissingEdgesError as e:
            print(f"\u274c Error: {map_path}: {e}")
            sys.exit(1)

        files.append({
            "name":          base.replace("_inst", ".c"),
            "html":          html_path,
            "source_html":   source_html if source_html_exists else None,
            "total_edges":   total_edges,
            "covered_edges": covered_edges,
            "pct":           pct,
        })
    return files

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "summary_assets")


def _asset(name, **values):
    """Read summary_assets/<name> and fill its @@key@@ placeholders."""
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        text = f.read().rstrip("\n")
    for key, value in values.items():
        text = text.replace("@@%s@@" % key, str(value))
    return text


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

    CSS = _asset("summary.css", bar_color=bar_color, overall_pct=f"{overall_pct:.1f}")
    JS  = _asset("summary.js")

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
{CSS}
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
{JS}
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
