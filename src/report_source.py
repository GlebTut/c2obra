#!/usr/bin/env python3
"""C²oBra report: syntax-highlighted source page with per-line coverage."""

import os, re


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
        if r["status"] == "FULL":
            line_status[ln] = ("full", r["branch_id"])
        elif r["status"] == "PARTIAL":
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
