#!/usr/bin/env python3
"""
C²oBra - Report Generator
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
        return None
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
            out += f'<span style="color:#16a34a">{tok}</span>'
        elif tok.startswith('"') or tok.startswith("'"):
            out += f'<span style="color:#ce9178">{tok}</span>'
        elif tok.startswith("#"):
            out += f'<span style="color:#c586c0">{tok}</span>'
        elif re.fullmatch(r'\d+', tok):
            out += f'<span style="color:#cbd5e1">{tok}</span>'
        elif re.fullmatch(keywords, tok):
            out += f'<span style="color:#16a34a">{tok}</span>'
        else:
            out += tok
    return out


# No logo image used
LOGO_SVG = ''


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
            bg      = {"full": "#0d2226", "partial": "#2d1f00", "none": "#2d0d0d"}[status]
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

    report_html_basename = os.path.basename(report_html_name)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Source \u2014 {os.path.basename(src_path)}</title>
<script>
  (function(){{
    const t=(function(){{try{{return localStorage.getItem("theme")}}catch(e){{return null}}}}())||"dark";
    document.documentElement.setAttribute("data-theme",t);
  }})();
</script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  :root{{
    --bg:#0e1518;--text:#e8f0ef;--border:#141c1e;
    --ln:#546e7a;--subtext:#94a3b8;--surface:#0b1214;
    --logo-text:#1a1a2e;
  }}
  [data-theme="light"]{{
    --bg:#f5f7fa;--text:#1a1a2e;--border:#e5e7eb;
    --ln:#94a3b8;--subtext:#555555;--surface:#ffffff;
    --logo-text:#0d2226;
  }}
  body{{background:var(--bg);color:var(--text);font-family:'Cascadia Code','Fira Code','Consolas',monospace;font-size:0.82rem;padding:0;transition:background 0.2s,color 0.2s}}
  .topbar{{display:flex;justify-content:space-between;align-items:center;padding:0.75rem 1.5rem;background:#0f172a;border-bottom:2px solid #16a34a}}
  .topbar-left{{display:flex;align-items:center;gap:1rem}}
  .topbar a.back{{color:#94a3b8;text-decoration:none;font-size:0.82rem;padding:0.3em 0.8em;border:1px solid rgba(38,166,154,0.3);border-radius:6px;transition:background 0.15s}}
  .topbar a.back:hover{{background:rgba(38,166,154,0.15)}}
  .topbar-right{{display:flex;align-items:center;gap:0.8rem}}
  .legend{{font-size:0.75rem;color:#94a3b8;display:flex;gap:0.8rem;align-items:center}}
  .toggle-btn{{background:rgba(38,166,154,0.15);border:1px solid rgba(38,166,154,0.3);color:#e8f0ef;padding:0.3em 0.8em;border-radius:6px;cursor:pointer;font-size:0.8rem}}
  .content{{padding:1rem 2rem}}
  .file-label{{font-size:0.78rem;color:var(--subtext);margin-bottom:0.8rem;padding:0.4rem 0.8rem;background:var(--surface);border:1px solid var(--border);border-radius:6px;display:inline-block}}
  pre{{background:var(--bg);border-radius:8px;overflow-x:auto;padding:0.5rem 0;border:1px solid var(--border)}}
  .src-line{{display:block;white-space:pre;line-height:1.5;padding:0 0.5rem;border-left:3px solid transparent;transition:background 0.1s}}
  .src-line:hover{{background:rgba(38,166,154,0.05)!important}}
  .src-line:target{{outline:2px solid #16a34a;border-radius:2px;animation:pulse 1.2s ease}}
  @keyframes pulse{{0%{{background:#0f172a!important}}100%{{background:inherit}}}}
  .ln{{color:var(--ln);user-select:none;margin-right:1.5rem;display:inline-block;min-width:2.5rem;text-align:right}}
  .cd{{color:var(--text)}}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-left">
    <a class="back" href="{report_html_basename}">\u2190 Back to Report</a>
  </div>
  <div class="topbar-right">
    <div class="legend">
      <span style="color:#16a34a">&#9679; FULL</span>
      <span style="color:#d97706">&#9680; PARTIAL</span>
      <span style="color:#dc2626">&#9675; NONE</span>
    </div>
    <span style="color:#546e7a;font-size:0.8rem">{os.path.basename(src_path)}</span>
    <button class="toggle-btn" id="themeBtn" onclick="toggleTheme()">&#9728;&#65039; Light</button>
  </div>
</div>
<div class="content">
<div class="file-label">&#128196; {src_path}</div>
<pre>{lines_html}</pre>
</div>
<script>
  (function(){{
    const t=(function(){{try{{return localStorage.getItem("theme")}}catch(e){{return null}}}}())||"dark";
    document.getElementById("themeBtn").textContent=t==="dark"?"\u2600\ufe0f Light":"\U0001f319 Dark";
  }})();
  function toggleTheme(){{
    const curr=document.documentElement.getAttribute("data-theme")||"dark";
    const next=curr==="dark"?"light":"dark";
    document.documentElement.setAttribute("data-theme",next);
    try{{localStorage.setItem("theme",next);}}catch(e){{}}
    document.getElementById("themeBtn").textContent=next==="dark"?"\u2600\ufe0f Light":"\U0001f319 Dark";
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

    _branch_rows = [{"type": r["type"], "true_count": r["true_count"], "false_count": r["false_count"]} for r in rows]
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
        if r["covered"]:
            row_class = "full"
        elif r["true_count"] > 0 or r["false_count"] > 0:
            row_class = "partial"
        else:
            row_class = "none"

        btype  = r["type"].replace("_statement", "").replace("_", "-")
        status = "FULL" if r["covered"] else ("PARTIAL" if r["true_count"] > 0 or r["false_count"] > 0 else "NONE")
        t_label = r.get("true_label",  "")
        f_label = r.get("false_label", "")

        t_badge = f'<span class="badge hit"  title="{t_label}">{r["true_count"]}</span>'  if r["true_count"]  > 0 else f'<span class="badge miss" title="{t_label}">0</span>'
        f_badge = f'<span class="badge hit"  title="{f_label}">{r["false_count"]}</span>' if r["false_count"] > 0 else f'<span class="badge miss" title="{f_label}">0</span>'

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
/* ── Reset ─────────────────────────────────────────────── */
*{{box-sizing:border-box;margin:0;padding:0}}

/* ── Colour tokens ──────────────────────────────────────── */
:root{{
  --bg:#0f172a;
  --surface:#1e293b;
  --surface2:#253858;
  --text:#f1f5f9;
  --subtext:#94a3b8;
  --border:#334155;
  --header-bg:#0f172a;
  --header-border:#334155;
  --primary:#569cd6;
  --primary-dark:#1e3a5f;
  --primary-light:#94a3b8;
  --row-full:#0f3320;    --row-full-h:#134a2c;
  --row-partial:#4a2500; --row-partial-h:#5e3000;
  --row-none:#4a0a0a;    --row-none-h:#600e0e;
  --badge-hit:#16a34a;   --badge-miss:#dc2626;
  --logo-text:#f1f5f9;
}}
[data-theme="light"]{{
  --bg:#f5f7fa;
  --surface:#ffffff;
  --surface2:#f1f5f9;
  --text:#1a1a2e;
  --subtext:#555555;
  --border:#e5e7eb;
  --header-bg:#1a1a2e;
  --header-border:#334155;
  --row-full:#bbf7d0;    --row-full-h:#86efac;
  --row-partial:#fde68a; --row-partial-h:#fcd34d;
  --row-none:#fecaca;    --row-none-h:#fca5a5;
  --badge-hit:#16a34a;   --badge-miss:#dc2626;
  --logo-text:#1a1a2e;
}}

/* ── Base ───────────────────────────────────────────────── */
body{{font-family:"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--text);transition:background 0.2s,color 0.2s;min-height:100vh}}

/* ── Topbar ─────────────────────────────────────────────── */
.topbar{{
  display:flex;justify-content:space-between;align-items:center;
  padding:0.7rem 2rem;
  background:var(--header-bg);
  border-bottom:2px solid var(--header-border);
  position:sticky;top:0;z-index:100;
}}
.topbar-left{{display:flex;align-items:center;gap:1rem}}
.topbar-right{{display:flex;align-items:center;gap:0.6rem}}
.nav-btn{{
  display:inline-block;padding:0.38em 0.9em;
  background:rgba(38,166,154,0.12);
  color:#cbd5e1;border:1px solid rgba(38,166,154,0.3);
  border-radius:7px;text-decoration:none;font-size:0.84rem;font-weight:500;
  transition:background 0.15s,color 0.15s;white-space:nowrap;
}}
.nav-btn:hover{{background:rgba(38,166,154,0.25);color:#e8f0ef}}
.toggle-btn{{
  background:rgba(38,166,154,0.12);border:1px solid rgba(38,166,154,0.3);
  color:#cbd5e1;padding:0.38em 0.9em;border-radius:7px;cursor:pointer;font-size:0.84rem;
  transition:background 0.15s;
}}
.toggle-btn:hover{{background:rgba(38,166,154,0.25)}}

/* ── Page wrapper ───────────────────────────────────────── */
.page{{max-width:1200px;margin:0 auto;padding:1.6rem 2rem 3rem}}

/* ── File subtitle ──────────────────────────────────────── */
.file-meta{{
  font-size:0.82rem;color:var(--subtext);margin-bottom:1.6rem;
  display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;
}}
.file-meta strong{{color:var(--text)}}
.file-meta .sep{{opacity:0.4}}

/* ── KPI cards ──────────────────────────────────────────── */
.cards{{display:flex;gap:1rem;margin-bottom:1.4rem;flex-wrap:wrap}}
.card{{
  background:var(--surface);border:1px solid var(--border);
  border-top:3px solid {bar_color};
  border-radius:10px;padding:1rem 1.4rem;
  box-shadow:0 2px 12px rgba(0,0,0,0.25);min-width:140px;flex:1;
}}
.card .val{{font-size:2rem;font-weight:800;line-height:1;letter-spacing:-0.5px}}
.card .lbl{{font-size:0.78rem;color:var(--subtext);margin-top:0.35rem;font-weight:500;text-transform:uppercase;letter-spacing:0.04em}}

/* ── Progress bar ───────────────────────────────────────── */
.bar-wrap{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:10px;padding:1.1rem 1.4rem;
  box-shadow:0 2px 12px rgba(0,0,0,0.2);margin-bottom:1.6rem;
}}
.bar-label{{display:flex;justify-content:space-between;margin-bottom:0.6rem;font-size:0.88rem;color:var(--subtext)}}
.bar-label strong{{color:var(--text)}}
.bar-bg{{background:var(--border);border-radius:999px;height:20px;overflow:hidden}}
.bar-fg{{
  background:linear-gradient(90deg,{bar_color},{bar_color}cc);
  border-radius:999px;height:20px;
  width:{pct:.1f}%;
  transition:width 0.8s cubic-bezier(.4,0,.2,1);
  position:relative;
}}
.bar-fg::after{{
  content:'';position:absolute;top:0;left:0;right:0;bottom:0;
  background:linear-gradient(90deg,transparent 60%,rgba(255,255,255,0.12));
  border-radius:999px;
}}

/* ── Section headings ───────────────────────────────────── */
.section-heading{{
  font-size:0.82rem;font-weight:700;color:var(--primary);
  text-transform:uppercase;letter-spacing:0.1em;
  margin:1.8rem 0 0.9rem;
  display:flex;align-items:center;gap:0.6rem;
}}
.section-heading::before{{
  content:'';display:inline-block;width:3px;height:1em;
  background:var(--primary);border-radius:2px;flex-shrink:0;
}}

/* ── Collapsible section ────────────────────────────────── */
.collapsible-section{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:10px;margin-bottom:1.2rem;
  box-shadow:0 2px 12px rgba(0,0,0,0.2);overflow:hidden;
}}
.section-toggle{{
  width:100%;display:flex;align-items:center;gap:0.8rem;
  padding:0.9rem 1.2rem;background:transparent;
  border:none;cursor:pointer;color:var(--text);
  font-size:0.95rem;font-weight:600;text-align:left;
  border-bottom:1px solid transparent;
  transition:background 0.15s,border-color 0.15s;
}}
.section-toggle:hover{{background:var(--surface2)}}
.collapsible-section.open .section-toggle{{border-bottom-color:var(--border)}}
.toggle-icon{{
  display:inline-block;font-size:0.75rem;color:var(--primary);
  transition:transform 0.25s;flex-shrink:0;
}}
.collapsible-section:not(.open) .toggle-icon{{transform:rotate(-90deg)}}
.section-toggle-title{{flex:1}}
.section-badge{{
  font-size:0.75rem;font-weight:600;padding:0.2em 0.7em;
  background:rgba(38,166,154,0.15);color:var(--primary);
  border-radius:999px;border:1px solid rgba(38,166,154,0.25);
}}
.section-body{{
  display:none;padding:1rem 1.2rem;
}}
.collapsible-section.open .section-body{{display:block}}

/* ── Info banner ────────────────────────────────────────── */
.info-banner{{
  background:var(--surface);border:1px solid var(--border);
  border-left:3px solid var(--primary);
  border-radius:0 8px 8px 0;padding:0.8rem 1.1rem;
  font-size:0.9rem;color:var(--subtext);
  display:flex;align-items:flex-start;gap:0.7rem;margin-bottom:1.2rem;
}}
.info-icon{{font-size:1.1rem;flex-shrink:0;margin-top:1px}}

/* ── Charts grid ────────────────────────────────────────── */
.charts-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1.1rem}}
.chart-card{{
  background:var(--surface);border:1px solid var(--border);
  border-top:2px solid {bar_color};
  border-radius:10px;padding:1.1rem 1.3rem 0.9rem;
  box-shadow:0 2px 12px rgba(0,0,0,0.2);
}}
.chart-title{{font-size:0.88rem;font-weight:700;color:var(--text);margin-bottom:2px}}
.chart-subtitle{{font-size:0.73rem;color:var(--subtext);margin-bottom:0.8rem}}
.chart-wrap{{position:relative;height:200px}}
.chart-legend{{display:flex;flex-wrap:wrap;gap:0.3rem 0.9rem;margin-top:0.65rem}}
.chart-legend-item{{display:flex;align-items:center;gap:5px;font-size:0.73rem;color:var(--subtext)}}
.chart-legend-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}

/* ── Controls ───────────────────────────────────────────── */
.controls{{display:flex;gap:0.7rem;margin-bottom:0.6rem;align-items:center;flex-wrap:wrap}}
.controls input{{
  padding:0.42em 0.8em;border:1px solid var(--border);
  border-radius:7px;font-size:0.88rem;width:220px;
  background:var(--surface);color:var(--text);
  transition:border-color 0.15s;
}}
.controls input:focus{{outline:none;border-color:var(--primary)}}
.controls select{{
  padding:0.42em 0.8em;border:1px solid var(--border);
  border-radius:7px;font-size:0.88rem;
  background:var(--surface);color:var(--text);
}}
.export-btn{{
  background:var(--surface);color:var(--primary);
  border:1px solid var(--primary);padding:0.42em 1em;
  border-radius:7px;cursor:pointer;font-size:0.84rem;
  margin-left:auto;font-weight:600;transition:background 0.15s;
}}
.export-btn:hover{{background:rgba(38,166,154,0.12)}}
.row-count{{font-size:0.8rem;color:var(--subtext);margin-bottom:0.7rem}}

/* ── Table ──────────────────────────────────────────────── */
.table-wrap{{overflow-x:auto;border-radius:10px;border:1px solid var(--border);box-shadow:0 2px 12px rgba(0,0,0,0.2)}}
table{{width:100%;border-collapse:collapse;background:var(--surface)}}
th{{
  background:#0f172a;color:#cbd5e1;
  padding:0.7em 1em;text-align:left;
  font-size:0.84rem;font-weight:600;
  cursor:pointer;user-select:none;white-space:nowrap;
  border-bottom:2px solid #16a34a;
}}
th:hover{{background:#4a90d9;color:#e8f0ef}}
th.sorted-asc::after{{content:" \u25b2";font-size:0.7em}}
th.sorted-desc::after{{content:" \u25bc";font-size:0.7em}}
td{{padding:0.52em 1em;font-size:0.93rem;border-bottom:1px solid var(--border)}}
tr:last-child td{{border-bottom:none}}
tr.full    {{background:var(--row-full)}}
tr.partial {{background:var(--row-partial)}}
tr.none    {{background:var(--row-none)}}
tr.full:hover    {{background:var(--row-full-h)}}
tr.partial:hover {{background:var(--row-partial-h)}}
tr.none:hover    {{background:var(--row-none-h)}}

/* ── Badges & status pills ──────────────────────────────── */
.badge{{display:inline-block;padding:0.15em 0.6em;border-radius:999px;font-size:0.83em;font-weight:700}}
.badge.hit  {{background:var(--badge-hit);color:#fff}}
.badge.miss {{background:var(--badge-miss);color:#fff}}
.status{{display:inline-block;padding:0.2em 0.65em;border-radius:6px;font-size:0.8em;font-weight:700}}
.status.full    {{background:#16a34a;color:#fff}}
.status.partial {{background:#d97706;color:#fff}}
.status.none    {{background:#dc2626;color:#fff}}
.run-status{{display:inline-block;padding:0.2em 0.65em;border-radius:6px;font-size:0.8em;font-weight:700}}
.run-status-pass    {{background:#16a34a;color:#fff}}
.run-status-partial {{background:#d97706;color:#fff}}
.run-status-timeout {{background:#dc2626;color:#fff}}
.run-status-crash   {{background:#78909c;color:#fff}}

/* ── Inputs table ───────────────────────────────────────── */
.inputs-table{{width:100%;border-collapse:collapse;font-size:0.9rem}}
.inputs-table th{{background:var(--surface2);color:var(--subtext);padding:0.5em 0.9em;text-align:left;font-size:0.8rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;border-bottom:1px solid var(--border);cursor:default}}
.inputs-table td{{padding:0.5em 0.9em;border-bottom:1px solid var(--border)}}
.inputs-table tr:last-child td{{border-bottom:none}}
.tc-cell{{color:var(--subtext);font-size:0.84rem;white-space:nowrap;width:200px}}
.input-code{{background:var(--surface2);padding:0.2em 0.5em;border-radius:4px;color:var(--text);font-size:0.93em}}

code{{background:var(--surface2);padding:0.15em 0.45em;border-radius:4px;font-size:0.93em}}
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
/* ── Theme toggle ───────────────────────────────────────── */
(function(){{
  const t=(function(){{try{{return localStorage.getItem("theme")}}catch(e){{return null}}}}())||"dark";
  document.getElementById("themeBtn").textContent=t==="dark"?"\u2600\ufe0f Light":"\U0001f319 Dark";
}})();
function toggleTheme(){{
  const curr=document.documentElement.getAttribute("data-theme")||"dark";
  const next=curr==="dark"?"light":"dark";
  document.documentElement.setAttribute("data-theme",next);
  try{{localStorage.setItem("theme",next);}}catch(e){{}}
  document.getElementById("themeBtn").textContent=next==="dark"?"\u2600\ufe0f Light":"\U0001f319 Dark";
}}

/* ── Collapsible sections ───────────────────────────────── */
function toggleSection(id){{
  const el=document.getElementById(id);
  const btn=el.querySelector(".section-toggle");
  const isOpen=el.classList.contains("open");
  el.classList.toggle("open",!isOpen);
  btn.setAttribute("aria-expanded",String(!isOpen));
}}
// open all by default already set via class

/* ── Table sort / filter ────────────────────────────────── */
let sortCol={status_col},sortAsc=true;
const STATUS_ORDER={{NONE:0,PARTIAL:1,FULL:2}};
function getStatus(row){{return row.getAttribute("data-status")||"";}}
(function defaultSort(){{
  const tbody=document.getElementById("tableBody");
  const rows=Array.from(tbody.querySelectorAll("tr"));
  rows.sort((a,b)=>(STATUS_ORDER[getStatus(a)]??9)-(STATUS_ORDER[getStatus(b)]??9));
  rows.forEach(r=>tbody.appendChild(r));
  document.querySelectorAll("th")[{status_col}].classList.add("sorted-asc");
  updateCount();
}})();
function sortTable(col){{
  const tbody=document.getElementById("tableBody");
  const rows=Array.from(tbody.querySelectorAll("tr"));
  if(sortCol===col)sortAsc=!sortAsc;else{{sortCol=col;sortAsc=true;}}
  rows.sort((a,b)=>{{
    if(col==={status_col}){{const av=STATUS_ORDER[getStatus(a)]??9,bv=STATUS_ORDER[getStatus(b)]??9;return sortAsc?av-bv:bv-av;}}
    const av=a.cells[col].innerText.trim(),bv=b.cells[col].innerText.trim();
    const an=parseFloat(av),bn=parseFloat(bv);
    const cmp=isNaN(an)||isNaN(bn)?av.localeCompare(bv):an-bn;
    return sortAsc?cmp:-cmp;
  }});
  rows.forEach(r=>tbody.appendChild(r));
  document.querySelectorAll("th").forEach((th,i)=>{{
    th.classList.remove("sorted-asc","sorted-desc");
    if(i===col)th.classList.add(sortAsc?"sorted-asc":"sorted-desc");
  }});
  updateCount();
}}
function applyFilters(){{
  const search=document.getElementById("search").value.toLowerCase();
  const filter=document.getElementById("filter").value;
  const rows=document.querySelectorAll("#tableBody tr");
  let visible=0;
  rows.forEach(r=>{{
    const text=r.innerText.toLowerCase();
    const status=r.getAttribute("data-status")||"";
    const ms=!search||text.includes(search);
    const mf=filter==="all"?true:filter==="uncovered"?status!=="FULL":status===filter;
    const show=ms&&mf;
    r.style.display=show?"":"none";
    if(show)visible++;
  }});
  updateCount(visible);
}}
function updateCount(n){{
  const total=document.querySelectorAll("#tableBody tr").length;
  const shown=n!==undefined?n:total;
  document.getElementById("rowCount").textContent=
    shown===total?`Showing all ${{total}} branches`:`Showing ${{shown}} of ${{total}} branches`;
}}
const HEADERS={headers_js};
function exportCSV(){{
  const rows=Array.from(document.querySelectorAll("#tableBody tr")).filter(r=>r.style.display!=="none");
  const lines=[HEADERS.join(",")];
  rows.forEach(r=>{{const cells=Array.from(r.cells).map(c=>JSON.stringify(c.innerText.trim()));lines.push(cells.join(","));}});
  const blob=new Blob([lines.join("\\n")],{{type:"text/csv"}});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="coverage.csv";a.click();
}}

/* ── Charts ─────────────────────────────────────────────── */
(function(){{
  if(typeof Chart==="undefined"){{
    document.querySelectorAll(".chart-wrap").forEach(el=>{{
      el.innerHTML="<p style=\\"color:#546e7a;font-size:0.8rem;text-align:center;margin-top:3.5rem\\">&#9888;&#65039; Chart.js unavailable (offline or CDN blocked)</p>";
    }});
    return;
  }}
  const isDark=document.documentElement.getAttribute("data-theme")!=="light";
  Chart.defaults.color=isDark?"#94a3b8":"#4a90d9";
  Chart.defaults.font.family="'Segoe UI',system-ui,sans-serif";
  Chart.defaults.font.size=11;
  const C={{
    full:"#16a34a",partial:"#d97706",none:"#dc2626",
    pass:"#16a34a",crash:"#78909c",timeout:"#dc2626",
    accent:"#94a3b8",accent2:"#1e293b"
  }};
  const rows={branch_rows_json};
  const inputs={test_inputs_json};

  /* 1. Donut — full/partial/none */
  (function(){{
    const full=rows.filter(r=>r.true_count>0&&r.false_count>0).length;
    const part=rows.filter(r=>(r.true_count>0)!==(r.false_count>0)).length;
    const none=rows.filter(r=>r.true_count===0&&r.false_count===0).length;
    const tot=rows.length;
    new Chart(document.getElementById("donutChart"),{{
      type:"doughnut",
      data:{{labels:["Full","Partial","Not covered"],datasets:[{{
        data:[full,part,none],
        backgroundColor:[C.full,C.partial,C.none],
        borderWidth:0,hoverOffset:8,
        borderRadius:3
      }}]}},
      options:{{
        responsive:true,maintainAspectRatio:false,cutout:"70%",
        animation:{{duration:800,easing:"easeOutQuart"}},
        plugins:{{
          legend:{{display:false}},
          tooltip:{{callbacks:{{label:ctx=>`  ${{ctx.label}}: ${{ctx.parsed}} (${{tot?(ctx.parsed/tot*100).toFixed(1):0}}%)`}}}}
        }}
      }}
    }});
    const leg=document.getElementById("donutLegend");
    [["Full",C.full,full],["Partial",C.partial,part],["Not covered",C.none,none]].forEach(([l,c,v])=>{{
      leg.innerHTML+=`<div class="chart-legend-item"><div class="chart-legend-dot" style="background:${{c}}"></div><span>${{l}}: <strong>${{v}}</strong> (${{tot?(v/tot*100).toFixed(1):0}}%)</span></div>`;
    }});
  }})();

  /* 2. Horizontal bar — coverage by type */
  (function(){{
    const m={{}};
    rows.forEach(r=>{{const t=r.type||"other";if(!m[t])m[t]={{tot:0,th:0,fh:0}};m[t].tot+=2;m[t].th+=r.true_count>0?1:0;m[t].fh+=r.false_count>0?1:0;}});
    const labels=Object.keys(m).sort();
    const pcts=labels.map(t=>m[t].tot?+((m[t].th+m[t].fh)/m[t].tot*100).toFixed(1):0);
    new Chart(document.getElementById("typeChart"),{{
      type:"bar",
      data:{{labels,datasets:[{{
        label:"Coverage %",data:pcts,
        backgroundColor:pcts.map(p=>p>=80?C.full:p>=50?C.partial:C.none),
        borderRadius:5,borderSkipped:false
      }}]}},
      options:{{
        indexAxis:"y",responsive:true,maintainAspectRatio:false,
        animation:{{duration:800,easing:"easeOutQuart"}},
        scales:{{
          x:{{min:0,max:100,grid:{{color:"rgba(38,166,154,0.08)"}},ticks:{{callback:v=>v+"%"}}}},
          y:{{grid:{{display:false}}}}
        }},
        plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.parsed.x}}%`}}}}}}
      }}
    }});
  }})();

  /* 4. Doughnut — test run statuses */
  (function(){{
    const cnt={{pass:0,partial:0,timeout:0,crash:0}};
    if(Array.isArray(inputs))inputs.forEach(t=>{{const s=(t.status||"pass").toLowerCase();if(s in cnt)cnt[s]++;else cnt.pass++;}});
    const tot=Object.values(cnt).reduce((a,b)=>a+b,0);
    if(!tot){{document.getElementById("statusChart").parentElement.innerHTML="<p style=\\"color:#546e7a;font-size:0.8rem;text-align:center;margin-top:3.5rem\\">No test run data</p>";return;}}
    new Chart(document.getElementById("statusChart"),{{
      type:"doughnut",
      data:{{labels:["Pass","Partial","Timeout","Crash"],datasets:[{{
        data:[cnt.pass,cnt.partial,cnt.timeout,cnt.crash],
        backgroundColor:[C.pass,C.partial,C.timeout,C.crash],
        borderWidth:0,hoverOffset:8,borderRadius:3
      }}]}},
      options:{{
        responsive:true,maintainAspectRatio:false,cutout:"70%",
        animation:{{duration:800,easing:"easeOutQuart"}},
        plugins:{{
          legend:{{position:"bottom",labels:{{boxWidth:9,boxHeight:9,padding:10}}}},
          tooltip:{{callbacks:{{label:ctx=>`  ${{ctx.label}}: ${{ctx.parsed}} (${{tot?(ctx.parsed/tot*100).toFixed(1):0}}%)`}}}}
        }}
      }}
    }});
  }})();
}})();
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"✓ Wrote HTML report to {output_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="C\u00b2oBra — Generate coverage HTML + CSV report")
    parser.add_argument("branch_map",    help="Path to branch_map.json")
    parser.add_argument("coverage",      help="Path to coverage.json")
    parser.add_argument("--output",      default="output/coverage_report.html", help="Output HTML file")
    parser.add_argument("--csv",         default="output/coverage_report.csv",  help="Output CSV file")
    parser.add_argument("--test-inputs", default="output/test_inputs_log.json", help="Path to test inputs log JSON")
    parser.add_argument("--no-summary",  action="store_true",
                        help="Hide Back to Summary button (single-file mode)")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    branch_map_data = load_branch_map(args.branch_map)
    coverage        = load_coverage(args.coverage)
    test_inputs     = load_test_inputs(args.test_inputs)
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
