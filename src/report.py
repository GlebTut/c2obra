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


def load_test_inputs(path):
    if not os.path.exists(path):
        return None          # ← None = "not available", [] = "available but empty"
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


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
            "true_label":  b.get("true_label",  ""),
            "false_label": b.get("false_label", ""),
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
            fieldnames += ["true_label", "false_label", "true_count", "false_count", "covered"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                row = {
                    "file":        source_file,
                    "branch_id":   r["branch_id"],
                    "line":        r["line"],
                    "type":        r["type"],
                    "true_label":  r.get("true_label",  ""),
                    "false_label": r.get("false_label", ""),
                    "true_count":  r["true_count"],
                    "false_count": r["false_count"],
                    "covered":     r["covered"],
                }
                if has_labels:
                    row["label"] = r.get("label", "")
                writer.writerow(row)
            total_edges   = len(rows) * 2
            covered_edges = sum(1 for r in rows if r["true_count"]  > 0) + \
                            sum(1 for r in rows if r["false_count"] > 0)
            pct = (covered_edges / total_edges * 100) if total_edges > 0 else 0
            summary = {
                "file": "SUMMARY", "branch_id": "", "line": "", "type": "",
                "true_label": "", "false_label": "",
                "true_count": "", "false_count": "",
                "covered": f"{pct:.1f}% ({covered_edges}/{total_edges} branches)",
            }
            if has_labels:
                summary["label"] = ""
            writer.writerow(summary)
        print(f"✓ Wrote CSV to {output_path}")
    except OSError as e:
        print(f"❌ Error: could not write {output_path}: {e}")
        sys.exit(1)


def highlight_c_syntax(code):
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
    src_path = branch_map_data.get("source_file", "")
    if not src_path:
        return False
    if not os.path.exists(src_path):
        basename = os.path.basename(src_path)
        for candidate in [basename, os.path.join("output", basename), os.path.join("src", basename)]:
            if os.path.exists(candidate):
                src_path = candidate
                break
        else:
            print(f"⚠️  Source file not found: {src_path} — skipping source view")
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

    # ── FIX Bug 1: use only the filename for the back link, not a path ──
    report_html_basename = os.path.basename(report_html_name)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Source — {os.path.basename(src_path)}</title>
<script>
  (function(){{
    const t = (function(){{try{{return localStorage.getItem("theme")}}catch(e){{return null}}}}()) || "dark";
    document.documentElement.setAttribute("data-theme", t);
  }})();
</script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0f172a; --text: #d4d4d4; --border: #334155;
    --ln: #475569; --subtext: #94a3b8; --surface: #1e293b;
  }}
  [data-theme="light"] {{
    --bg: #f5f7fa; --text: #1a1a2e; --border: #e5e7eb;
    --ln: #aaa; --subtext: #555; --surface: #ffffff;
  }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 0.82rem; padding: 1rem 2rem;
    transition: background 0.2s, color 0.2s;
  }}
  .topbar {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 1rem; padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
  }}
  .topbar a {{ color: #569cd6; text-decoration: none; font-size: 0.85rem; }}
  .topbar a:hover {{ text-decoration: underline; }}
  .legend {{ font-size: 0.75rem; color: var(--subtext); display: flex; gap: 1rem; align-items: center; }}
  .legend span {{ display: flex; align-items: center; gap: 0.3rem; }}
  .toggle-btn {{ background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 0.3em 0.8em; border-radius: 6px; cursor: pointer; font-size: 0.8rem; margin-left: 1rem; }}
  pre {{ background: var(--bg); border-radius: 6px; overflow-x: auto; padding: 0.5rem 0; }}
  .src-line {{
    display: block; white-space: pre; line-height: 1.4;
    padding: 0 0.5rem; border-left: 3px solid transparent;
  }}
  .src-line:target {{ outline: 2px solid #569cd6; border-radius: 2px; animation: pulse 1.2s ease; }}
  @keyframes pulse {{
    0%   {{ background: #264f78 !important; }}
    100% {{ background: inherit; }}
  }}
  .ln {{ color: var(--ln); user-select: none; margin-right: 1.5rem; display: inline-block; min-width: 2.5rem; text-align: right; }}
  .cd {{ color: var(--text); }}
</style>
</head>
<body>
<div class="topbar">
  <a href="{report_html_basename}">← Back to Report</a>
  <span style="color:var(--subtext);font-size:0.85rem">{os.path.basename(src_path)}</span>
  <div class="legend">
    <span><span style="color:#16a34a">●</span> FULL</span>
    <span><span style="color:#d97706">◐</span> PARTIAL</span>
    <span><span style="color:#dc2626">○</span> NONE</span>
    <button class="toggle-btn" id="themeBtn" onclick="toggleTheme()">☀️ Light</button>
  </div>
</div>
<pre>{lines_html}</pre>
<script>
  (function(){{
    const t = (function(){{try{{return localStorage.getItem("theme")}}catch(e){{return null}}}}()) || "dark";
    document.getElementById("themeBtn").textContent = t === "dark" ? "☀️ Light" : "🌙 Dark";
  }})();
  function toggleTheme() {{
    const curr = document.documentElement.getAttribute("data-theme") || "dark";
    const next = curr === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try{{ localStorage.setItem("theme", next); }}catch(e){{}}
    document.getElementById("themeBtn").textContent = next === "dark" ? "☀️ Light" : "🌙 Dark";
  }}
</script>
</body>
</html>"""

    with open(source_html_path, "w") as f:
        f.write(html)
    print(f"✓ Wrote source view to {source_html_path}")
    return True


def write_html(rows, output_path, source_file, source_html_name=None, test_inputs=None, no_summary=False):
    total_edges   = len(rows) * 2
    covered_true  = sum(1 for r in rows if r["true_count"]  > 0)
    covered_false = sum(1 for r in rows if r["false_count"] > 0)
    covered_edges = covered_true + covered_false
    pct      = (covered_edges / total_edges * 100) if total_edges > 0 else 0
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    bar_color = "#16a34a" if pct >= 80 else "#d97706" if pct >= 50 else "#dc2626"

    # ── FIX Bug 1: use only basename for summary link so it works after ZIP extract ──
    if no_summary:
      back_button = ''
    else:
      back_button = '<a href="summary_report.html" style="display:inline-block;margin-bottom:1.2rem;padding:0.45rem 1.1rem;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;text-decoration:none;font-size:0.88rem;font-weight:500;">← Back to Summary</a>'

    source_btn = ""
    if source_html_name:
        # use only the basename — works when all files sit in the same flat folder
        src_basename = os.path.basename(source_html_name)
        source_btn = f' <a href="{src_basename}" style="display:inline-block;margin-bottom:1.2rem;margin-left:0.5rem;padding:0.45rem 1.1rem;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;text-decoration:none;font-size:0.88rem;">📄 View Source</a>'

    # ── FIX Bug 2: show a friendly banner when inputs are unavailable (None)
    #              vs. show the table when inputs exist (list, even if empty)
    if test_inputs is None:
        # Sikraken was not run — show informational banner
        inputs_html = """
<div style="margin-bottom:1.5em;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:0.9em 1.2em;box-shadow:0 2px 8px rgba(0,0,0,0.3);display:flex;align-items:center;gap:0.75em;color:var(--subtext);font-size:0.92em;">
  <span style="font-size:1.2em">ℹ️</span>
  <span>No test inputs available — Sikraken was not run (CI mode or no <code style="background:var(--border);padding:0.15em 0.5em;border-radius:4px">__VERIFIER_nondet</code> calls). Binary was executed once with no inputs.</span>
</div>"""
    elif len(test_inputs) == 0:
        inputs_html = """
<div style="margin-bottom:1.5em;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:0.9em 1.2em;color:var(--subtext);font-size:0.92em;">
  ℹ️ Test inputs log is empty.
</div>"""
    else:
        input_rows = "".join(
            f'<tr>'
            f'<td style="padding:0.5em 1em;border-bottom:1px solid var(--border);color:var(--text);width:220px;white-space:nowrap">{t["test_case"]}</td>'
            f'<td style="padding:0.5em 1em;border-bottom:1px solid var(--border);color:var(--text)"><code style="background:var(--border);padding:0.2em 0.6em;border-radius:4px;color:var(--text);font-size:1em">{ ", ".join(t["inputs"]) if t["inputs"] else "(no inputs)" }</code></td>'
            f'<td style="padding:0.5em 1em;border-bottom:1px solid var(--border)"><span class="run-status run-status-{t.get("status","pass")}">{t.get("status","pass").upper()}</span></td>'
            f'</tr>'
            for t in test_inputs
        )
        inputs_html = f"""
<details style="margin-bottom:1.5em;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:0.9em 1.2em;box-shadow:0 2px 8px rgba(0,0,0,0.3)">
  <summary style="cursor:pointer;font-weight:600;font-size:1.05em;user-select:none;color:var(--text)">
    📋 Test Inputs ({len(test_inputs)} test case{"s" if len(test_inputs) != 1 else ""})
  </summary>
  <table style="margin-top:0.75rem;width:100%;border-collapse:collapse;font-size:1em">
    <thead><tr>
      <th style="text-align:left;padding:0.5em 1em;color:var(--subtext);border-bottom:1px solid var(--border);font-weight:500;font-size:1em">Test Case</th>
      <th style="text-align:left;padding:0.5em 1em;color:var(--subtext);border-bottom:1px solid var(--border);font-weight:500;font-size:1em">Inputs</th>
      <th style="text-align:left;padding:0.5em 1em;color:var(--subtext);border-bottom:1px solid var(--border);font-weight:500;font-size:1em">Status</th>
    </tr></thead>
    <tbody>{input_rows}</tbody>
  </table>
</details>"""

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

        btype    = r["type"].replace("_statement", "").replace("_", "-")
        status   = "FULL" if r["covered"] else ("PARTIAL" if r["true_count"] > 0 or r["false_count"] > 0 else "NONE")
        t_label  = r.get("true_label",  "")
        f_label  = r.get("false_label", "")

        t_badge = f'<span class="badge hit"  title="{t_label}">{r["true_count"]}</span>'  if r["true_count"]  > 0 else f'<span class="badge miss" title="{t_label}">0</span>'
        f_badge = f'<span class="badge hit"  title="{f_label}">{r["false_count"]}</span>' if r["false_count"] > 0 else f'<span class="badge miss" title="{f_label}">0</span>'

        edge_label_html = ""
        if t_label and f_label:
            t_color = "#4ade80" if r["true_count"]  > 0 else "#f87171"
            f_color = "#4ade80" if r["false_count"] > 0 else "#f87171"
            edge_label_html = (
                f'<div style="font-size:0.75em;margin-top:0.3em;opacity:0.8;line-height:1.4">'
                f'<span style="color:{t_color}">T: {t_label}</span>'
                f'<span style="margin:0 0.4em;opacity:0.4">|</span>'
                f'<span style="color:{f_color}">F: {f_label}</span>'
                f'</div>'
            )

        label_td = f'<td><code>{r.get("label","")}</code></td>' if has_labels else ""

        # ── FIX Bug 1: source link uses basename only ──
        src_basename_for_link = os.path.basename(source_html_name) if source_html_name else ""
        src_link = f'{src_basename_for_link}#line-{r["line"]}' if src_basename_for_link and r["line"] != "?" else ""
        onclick  = f'onclick="window.open(\'{src_link}\',\'_blank\')"' if src_link else ""
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

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Coverage Report — {os.path.basename(source_file)}</title>
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
  body {{ font-family:"Segoe UI",Arial,sans-serif; background:var(--bg); color:var(--text); padding:2em; transition:background 0.2s,color 0.2s; }}
  h1 {{ font-size:1.5em; margin-bottom:0.2em; }}
  .subtitle {{ color:var(--subtext); font-size:0.9em; margin-bottom:1.5em; }}
  .topbar {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5em; }}
  .toggle-btn {{ background:var(--surface); border:1px solid var(--border); color:var(--text); padding:0.4em 0.9em; border-radius:6px; cursor:pointer; font-size:0.85em; }}
  .cards {{ display:flex; gap:1em; margin-bottom:1.5em; flex-wrap:wrap; }}
  .card {{ background:var(--surface); border-radius:10px; padding:1em 1.5em; box-shadow:0 2px 8px rgba(0,0,0,0.2); min-width:150px; border:1px solid var(--border); }}
  .card .val {{ font-size:1.8em; font-weight:bold; }}
  .card .lbl {{ font-size:0.8em; color:var(--subtext); margin-top:0.2em; }}
  .bar-wrap {{ background:var(--surface); border-radius:10px; padding:1.2em 1.5em; box-shadow:0 2px 8px rgba(0,0,0,0.2); margin-bottom:1.5em; border:1px solid var(--border); }}
  .bar-label {{ display:flex; justify-content:space-between; margin-bottom:0.5em; font-size:0.9em; color:var(--subtext); }}
  .bar-bg {{ background:var(--border); border-radius:999px; height:22px; }}
  .bar-fg {{ background:{bar_color}; border-radius:999px; height:22px; width:{pct:.1f}%; }}
  .controls {{ display:flex; gap:0.8em; margin-bottom:0.6em; align-items:center; flex-wrap:wrap; }}
  .controls input  {{ padding:0.4em 0.8em; border:1px solid var(--border); border-radius:6px; font-size:0.9em; width:240px; background:var(--surface); color:var(--text); }}
  .controls select {{ padding:0.4em 0.8em; border:1px solid var(--border); border-radius:6px; font-size:0.9em; background:var(--surface); color:var(--text); }}
  .row-count {{ font-size:0.82em; color:var(--subtext); margin-bottom:0.8em; }}
  table {{ width:100%; border-collapse:collapse; background:var(--surface); border-radius:10px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.2); border:1px solid var(--border); }}
  th {{ background:var(--header); color:#fff; padding:0.75em 1em; text-align:left; font-size:0.92em; cursor:pointer; user-select:none; white-space:nowrap; }}
  th:hover {{ background:var(--header-hover); }}
  th.sorted-asc::after  {{ content:" ▲"; font-size:0.75em; }}
  th.sorted-desc::after {{ content:" ▼"; font-size:0.75em; }}
  td {{ padding:0.55em 1em; font-size:0.95em; border-bottom:1px solid var(--border); }}
  tr:last-child td {{ border-bottom:none; }}
  tr.full    {{ background:var(--row-full); }}
  tr.partial {{ background:var(--row-partial); }}
  tr.none    {{ background:var(--row-none); }}
  tr.full:hover    {{ background:var(--row-full-hover); }}
  tr.partial:hover {{ background:var(--row-partial-hover); }}
  tr.none:hover    {{ background:var(--row-none-hover); }}
  .badge {{ display:inline-block; padding:0.15em 0.6em; border-radius:999px; font-size:0.85em; font-weight:bold; }}
  .badge.hit  {{ background:#16a34a; color:#fff; }}
  .badge.miss {{ background:#dc2626; color:#fff; }}
  .status {{ display:inline-block; padding:0.2em 0.7em; border-radius:6px; font-size:0.82em; font-weight:bold; }}
  .status.full    {{ background:#16a34a; color:#fff; }}
  .status.partial {{ background:#d97706; color:#fff; }}
  .status.none    {{ background:#dc2626; color:#fff; }}
  .run-status {{ display:inline-block; padding:0.2em 0.7em; border-radius:6px; font-size:0.82em; font-weight:bold; }}
  .run-status-pass    {{ background:#16a34a; color:#fff; }}
  .run-status-partial {{ background:#d97706; color:#fff; }}
  .run-status-timeout {{ background:#dc2626; color:#fff; }}
  .run-status-crash   {{ background:#9ca3af; color:#fff; }}
  code {{ background:var(--border); padding:0.15em 0.5em; border-radius:4px; font-size:0.95em; }}
  .export-btn {{ background:var(--surface); color:var(--text); border:1px solid var(--border); padding:0.4em 1em; border-radius:6px; cursor:pointer; font-size:0.85em; margin-left:auto; }}
  .export-btn:hover {{ background:var(--border); }}
</style>
</head>
<body>
{back_button}{source_btn}
<div class="topbar">
  <div>
    <h1>🔍 Coverage Report</h1>
    <p class="subtitle"><strong>File:</strong> {source_file} &nbsp;|&nbsp; <strong>Generated:</strong> {date_str}</p>
  </div>
  <button class="toggle-btn" id="themeBtn" onclick="toggleTheme()">☀️ Light</button>
</div>
<div class="cards">
  <div class="card"><div class="val">{total_edges}</div><div class="lbl">Total branches</div></div>
  <div class="card"><div class="val">{covered_edges}</div><div class="lbl">Covered branches</div></div>
  <div class="card"><div class="val" style="color:{bar_color}">{pct:.1f}%</div><div class="lbl">Branch coverage</div></div>
</div>
<div class="bar-wrap">
  <div class="bar-label"><span>Branch Coverage</span><span>{covered_edges}/{total_edges} branches</span></div>
  <div class="bar-bg"><div class="bar-fg"></div></div>
</div>
{inputs_html}
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
  (function(){{
    const t = (function(){{try{{return localStorage.getItem("theme")}}catch(e){{return null}}}}()) || "dark";
    document.getElementById("themeBtn").textContent = t === "dark" ? "☀️ Light" : "🌙 Dark";
  }})();
  function toggleTheme() {{
    const curr = document.documentElement.getAttribute("data-theme") || "dark";
    const next = curr === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try{{ localStorage.setItem("theme", next); }}catch(e){{}}
    document.getElementById("themeBtn").textContent = next === "dark" ? "☀️ Light" : "🌙 Dark";
  }}
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
    const search = document.getElementById("search").value.toLowerCase();
    const filter = document.getElementById("filter").value;
    const rows   = document.querySelectorAll("#tableBody tr");
    let visible  = 0;
    rows.forEach(r => {{
      const text   = r.innerText.toLowerCase();
      const status = r.getAttribute("data-status") || "";
      const matchSearch = !search || text.includes(search);
      const matchFilter =
        filter === "all"       ? true :
        filter === "uncovered" ? status !== "FULL" :
        status === filter;
      const show = matchSearch && matchFilter;
      r.style.display = show ? "" : "none";
      if (show) visible++;
    }});
    updateCount(visible);
  }}
  function updateCount(n) {{
    const total = document.querySelectorAll("#tableBody tr").length;
    const shown = n !== undefined ? n : total;
    document.getElementById("rowCount").textContent =
      shown === total ? `Showing all ${{total}} branches` : `Showing ${{shown}} of ${{total}} branches`;
  }}
  const HEADERS = {headers_js};
  function exportCSV() {{
    const rows = Array.from(document.querySelectorAll("#tableBody tr"))
                      .filter(r => r.style.display !== "none");
    const lines = [HEADERS.join(",")];
    rows.forEach(r => {{
      const cells = Array.from(r.cells).map(c => JSON.stringify(c.innerText.trim()));
      lines.push(cells.join(","));
    }});
    const blob = new Blob([lines.join("\\n")], {{type:"text/csv"}});
    const a    = document.createElement("a");
    a.href     = URL.createObjectURL(blob);
    a.download = "coverage.csv";
    a.click();
  }}
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"✓ Wrote HTML report to {output_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate coverage HTML + CSV report")
    parser.add_argument("branch_map",    help="Path to branch_map.json")
    parser.add_argument("coverage",      help="Path to coverage.json")
    parser.add_argument("--output",      default="output/coverage_report.html", help="Output HTML file")
    parser.add_argument("--csv",         default="output/coverage_report.csv",  help="Output CSV file")
    parser.add_argument("--test-inputs", default="output/test_inputs_log.json", help="Path to test inputs log JSON")
    parser.add_argument('--no-summary', action='store_true',
                    help='Hide Back to Summary button (single-file mode)')
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    branch_map_data = load_branch_map(args.branch_map)
    coverage        = load_coverage(args.coverage)
    test_inputs     = load_test_inputs(args.test_inputs)   # None if file missing
    rows            = merge(branch_map_data, coverage)

    source_file      = branch_map_data.get("source_file", "unknown")
    base             = os.path.splitext(args.output)[0]
    source_html_path = base.removesuffix("_report") + "_source.html"
    source_html_name = os.path.basename(source_html_path)

    wrote_source = write_source_html(rows, branch_map_data, source_html_path, os.path.basename(args.output))

    write_html(rows, args.output, source_file,
              source_html_name=source_html_name if wrote_source else None,
              test_inputs=test_inputs,
              no_summary=args.no_summary)
    write_csv(rows, args.csv, source_file)


if __name__ == "__main__":
    main()
