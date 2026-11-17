#!/usr/bin/env python3
"""C²oBra report: main HTML page. CSS and JavaScript live in src/report_assets/."""

import json, os
from datetime import datetime

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_assets")


def _asset(name, **values):
    """Read report_assets/<name> and fill its @@key@@ placeholders."""
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        text = f.read().rstrip("\n")
    for key, value in values.items():
        text = text.replace("@@%s@@" % key, str(value))
    return text



def write_html(rows, totals, output_path, source_file, source_html_name=None, test_inputs=None, no_summary=False):
    """totals: (covered edges, total edges) from edges.edge_coverage()."""
    covered_edges, total_edges = totals
    pct      = (covered_edges / total_edges * 100) if total_edges > 0 else 0
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    bar_color = "#16a34a" if pct >= 80 else "#d97706" if pct >= 50 else "#dc2626"

    back_button = "" if no_summary else '<a href="summary_report.html" class="nav-btn">\u2190 Back to Summary</a>'

    source_btn = ""
    if source_html_name:
        src_basename = os.path.basename(source_html_name)
        source_btn = f'<a href="{src_basename}" class="nav-btn">&#128196; View Source</a>'

    # ── Test inputs section (collapsible) ────────────────────────────────────
    if test_inputs is None:
        inputs_html = """
<div class="info-banner">
  <span class="info-icon">&#8505;&#65039;</span>
  <span>No test inputs available \u2014 Sikraken was not run (CI mode or no <code>__VERIFIER_nondet</code> calls). Binary was executed once with no inputs.</span>
</div>"""
    elif len(test_inputs) == 0:
        inputs_html = """
<div class="info-banner">
  <span class="info-icon">&#8505;&#65039;</span>
  <span>Test inputs log is empty.</span>
</div>"""
    else:
        input_rows = "".join(
            f'<tr>'
            f'<td class="tc-cell">{t["test_case"]}</td>'
            f'<td><code class="input-code">{ ", ".join(t["inputs"]) if t["inputs"] else "(no inputs)" }</code></td>'
            f'<td><span class="run-status run-status-{t.get("status","pass")}">{t.get("status","pass").upper()}</span></td>'
            f'</tr>'
            for t in test_inputs
        )
        inputs_html = f"""
<div class="collapsible-section" id="inputs-section">
  <button class="section-toggle" onclick="toggleSection('inputs-section')" aria-expanded="true">
    <span class="toggle-icon">&#9660;</span>
    <span class="section-toggle-title">&#128203; Test Inputs</span>
    <span class="section-badge">{len(test_inputs)} test case{"s" if len(test_inputs) != 1 else ""}</span>
  </button>
  <div class="section-body">
    <table class="inputs-table">
      <thead><tr>
        <th>Test Case</th><th>Inputs</th><th>Status</th>
      </tr></thead>
      <tbody>{input_rows}</tbody>
    </table>
  </div>
</div>"""

    _branch_rows = [{"type": r["type"], "status": r["status"],
                     "edges_hit": r["edges_hit"], "edges_total": r["edges_total"]} for r in rows]
    branch_rows_json = json.dumps(_branch_rows)
    test_inputs_json = json.dumps(test_inputs) if isinstance(test_inputs, list) else "[]"

    has_labels  = any(r.get("label") for r in rows)
    status_col  = 6 if has_labels else 5
    label_th    = '<th onclick="sortTable(3)">Case</th>' if has_labels else ""
    tc_idx      = 4 if has_labels else 3
    fc_idx      = 5 if has_labels else 4
    headers_js  = '["ID","Line","Type","Case","True hits","False hits","Status"]' if has_labels else '["ID","Line","Type","True hits","False hits","Status"]'

    table_rows = ""
    for r in rows:
        row_class = {"FULL": "full", "PARTIAL": "partial"}.get(r["status"], "none")

        btype  = r["type"].replace("_statement", "").replace("_", "-")
        status = r["status"]
        t_label = r.get("true_label",  "")
        f_label = r.get("false_label", "")

        t_badge = f'<span class="badge hit"  title="{t_label}">{r["true_count"]}</span>'  if r["true_count"]  > 0 else f'<span class="badge miss" title="{t_label}">0</span>'
        f_badge = f'<span class="badge hit"  title="{f_label}">{r["false_count"]}</span>' if r["false_count"] > 0 else f'<span class="badge miss" title="{f_label}">0</span>'
        # A counter side that is not an edge (a switch label's false side): show its count, greyed out
        if not r["true_edge"]:
            t_badge = f'<span class="badge" style="opacity:0.45" title="not an edge">{r["true_count"]}</span>'
        if not r["false_edge"]:
            f_badge = f'<span class="badge" style="opacity:0.45" title="not an edge (switch label: only its true edge counts)">{r["false_count"]}</span>'

        edge_label_html = ""
        if t_label and f_label:
            t_color = "#16a34a" if r["true_count"]  > 0 else "#ef9a9a"
            f_color = "#16a34a" if r["false_count"] > 0 else "#ef9a9a"
            edge_label_html = (
                f'<div style="font-size:0.73em;margin-top:0.3em;opacity:0.85;line-height:1.4">'
                f'<span style="color:{t_color}">T: {t_label}</span>'
                f'<span style="margin:0 0.4em;opacity:0.4">|</span>'
                f'<span style="color:{f_color}">F: {f_label}</span>'
                f'</div>'
            )

        label_td = f'<td><code>{r.get("label","")}</code></td>' if has_labels else ""

        src_basename_for_link = os.path.basename(source_html_name) if source_html_name else ""
        src_link = f'{src_basename_for_link}#line-{r["line"]}' if src_basename_for_link and r["line"] != "?" else ""
        onclick  = f"onclick=\"window.open('{src_link}','_blank')\"" if src_link else ""
        cursor   = 'style="cursor:pointer"' if src_link else ""

        table_rows += (
            f'<tr class="{row_class}" data-status="{status}" {onclick} {cursor}>'
            f'<td>{r["branch_id"]}</td>'
            f'<td>{r["line"]}</td>'
            f'<td><code>{btype}</code>{edge_label_html}</td>'
            f'{label_td}'
            f'<td>{t_badge}</td>'
            f'<td>{f_badge}</td>'
            f'<td><span class="status {row_class}">{status}</span></td>'
            f'</tr>'
        )

    CSS = _asset("report.css", bar_color=bar_color, pct=f"{pct:.1f}")
    JS  = _asset("report.js", status_col=status_col, headers_js=headers_js,
                 branch_rows_json=branch_rows_json, test_inputs_json=test_inputs_json,
                 tc_idx=tc_idx, fc_idx=fc_idx)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>C\u00b2oBra \u2014 {os.path.basename(source_file)}</title>
<script>
  (function(){{
    const t=(function(){{try{{return localStorage.getItem("theme")}}catch(e){{return null}}}}())||"dark";
    document.documentElement.setAttribute("data-theme",t);
  }})();
</script>
<style>
{CSS}
</style>
</head>
<body>

<!-- ── Topbar ────────────────────────────────────────────── -->
<div class="topbar">
  <div class="topbar-left">
    {back_button}
    {source_btn}
  </div>
  <div class="topbar-right">
    <button class="toggle-btn" id="themeBtn" onclick="toggleTheme()">\u2600\ufe0f Light</button>
  </div>
</div>

<div class="page">

<!-- ── File meta ─────────────────────────────────────────── -->
<div class="file-meta">
  <strong>{source_file}</strong>
  <span class="sep">&nbsp;|&nbsp;</span>
  Generated: {date_str}
</div>

<!-- ── KPI cards ─────────────────────────────────────────── -->
<div class="cards">
  <div class="card">
    <div class="val">{total_edges}</div>
    <div class="lbl">Total branches</div>
  </div>
  <div class="card">
    <div class="val">{covered_edges}</div>
    <div class="lbl">Covered branches</div>
  </div>
  <div class="card">
    <div class="val" style="color:{bar_color}">{pct:.1f}%</div>
    <div class="lbl">Branch coverage</div>
  </div>
  <div class="card">
    <div class="val">{total_edges - covered_edges}</div>
    <div class="lbl">Uncovered branches</div>
  </div>
</div>

<!-- ── Progress bar ──────────────────────────────────────── -->
<div class="bar-wrap">
  <div class="bar-label">
    <span><strong>Branch Coverage</strong></span>
    <span>{covered_edges}/{total_edges} branches &nbsp;&mdash;&nbsp; <strong style="color:{bar_color}">{pct:.1f}%</strong></span>
  </div>
  <div class="bar-bg"><div class="bar-fg"></div></div>
</div>

<!-- ── Analytics (collapsible) ───────────────────────────── -->
<div class="section-heading">Analytics</div>
<div class="collapsible-section" id="analytics-section">
  <button class="section-toggle" onclick="toggleSection('analytics-section')" aria-expanded="true">
    <span class="toggle-icon">&#9660;</span>
    <span class="section-toggle-title">&#128202; Coverage Charts</span>
    <span class="section-badge">3 charts</span>
  </button>
  <div class="section-body">
    <div class="charts-grid">
      <div class="chart-card">
        <div class="chart-title">Branch Coverage Breakdown</div>
        <div class="chart-subtitle">Full / Partial / Not covered</div>
        <div class="chart-wrap"><canvas id="donutChart"></canvas></div>
        <div class="chart-legend" id="donutLegend"></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">Coverage by Branch Type</div>
        <div class="chart-subtitle">% edges covered per construct</div>
        <div class="chart-wrap"><canvas id="typeChart"></canvas></div>
      </div>

      <div class="chart-card">
        <div class="chart-title">Test Run Statuses</div>
        <div class="chart-subtitle">Outcome of each test case</div>
        <div class="chart-wrap"><canvas id="statusChart"></canvas></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Test Inputs (collapsible) ─────────────────────────── -->
<div class="section-heading">Test Inputs</div>
{inputs_html}

<!-- ── Branch Details (collapsible) ──────────────────────── -->
<div class="section-heading">Branch Details</div>
<div class="collapsible-section open" id="branches-section">
  <button class="section-toggle" onclick="toggleSection('branches-section')" aria-expanded="true">
    <span class="toggle-icon">&#9660;</span>
    <span class="section-toggle-title">&#128336; Branch Table</span>
    <span class="section-badge">{len(rows)} branches</span>
  </button>
  <div class="section-body">
    <div class="controls">
      <input type="text" id="search" placeholder="&#128269; Search by line or type\u2026" oninput="applyFilters()">
      <select id="filter" onchange="applyFilters()">
        <option value="all">All statuses</option>
        <option value="FULL">FULL only</option>
        <option value="PARTIAL">PARTIAL only</option>
        <option value="NONE">NONE only</option>
        <option value="uncovered">Hide fully covered</option>
      </select>
      <button class="export-btn" onclick="exportCSV()">&#8595; Download CSV</button>
    </div>
    <div class="row-count" id="rowCount"></div>
    <div class="table-wrap">
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
    </div>
  </div>
</div>

</div><!-- /.page -->

<!-- Chart.js -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
{JS}
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"✓ Wrote HTML report to {output_path}")
