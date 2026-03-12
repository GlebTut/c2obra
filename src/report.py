#!/usr/bin/env python3
"""
C Testing Coverage Tool - Report Generator
Reads branch_map.json + coverage.json and outputs HTML + CSV reports
"""

import sys, json, os, csv
from datetime import datetime

def load_branch_map(path):
    with open(path) as f:
        return json.load(f)["branches"]

def load_coverage(path):
    """Returns dict: {branch_id: {"true": N, "false": N}}"""
    if not os.path.exists(path):
        print("⚠️  Warning: coverage file not found — treating all branches as uncovered")
        return {}
    with open(path) as f:
        data = json.load(f)
    
    # Support both raw coverage.json and aggregated coverage_report.json
    branches = data.get("branches", [])
    return {entry["id"]: entry for entry in branches}

def merge(branch_map, coverage):
    """Merge branch metadata with hit counts"""
    rows = []
    for b in branch_map:
        bid = b["id"]
        hits = coverage.get(bid, {})
        true_count = hits.get("true", 0)
        false_count = hits.get("false", 0)
        if "covered" in hits:
            covered = hits["covered"]          # trust run_tests.py's definition
        else:
            covered = true_count > 0 and false_count > 0  # both sides must be hit

        rows.append({
            "branch_id":    bid,
            "line":         b.get("line", "?"),
            "type":         b.get("type", "?"),
            "label":        b.get("label", ""),
            "true_count":   true_count,
            "false_count":  false_count,
            "covered":      covered,
        })
    return rows

def write_csv(rows, output_path, source_file):
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "file",
            "branch_id",
            "line",
            "type",
            "label",
            "true_count",
            "false_count",
            "covered"
        ])
        writer.writeheader()
        for r in rows:
            writer.writerow({"file": source_file, **r})
    print(f"✓ Wrote CSV to {output_path}")

def write_html(rows, output_path, source_file):
    total = len(rows)
    covered = sum (1 for r in rows if r["covered"])
    pct = (covered / total * 100) if total > 0 else 0
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Build table rows
    table_rows = ""
    for r in rows:
        if r["covered"]:
            color = ""                          # white — fully covered
        elif r["true_count"] > 0 or r["false_count"] > 0:
            color = ' style="background:#fff3cd"'  # yellow — partial
        else:
            color = ' style="background:#ffe0e0"'  # red — never hit
        label = r["label"] or "-"
        table_rows += (
            f'<tr{color}>'
            f'<td>{r["branch_id"]}</td>'
            f'<td>{r["line"]}</td>'
            f'<td>{r["type"]}</td>'
            f'<td>{label}</td>'
            f'<td>{r["true_count"]}</td>'
            f'<td>{r["false_count"]}</td>'
            f'<td>{"✅" if r["covered"] else "❌"}</td>'
            f'</tr>\n'
        )
        
    html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <title>Coverage Report — {os.path.basename(source_file)}</title>
    <style>
    body {{ font-family: sans-serif; margin: 2em; color: #222; }}
        h1   {{ font-size: 1.4em; }}
        .summary {{ margin: 1em 0; }}
        .bar-bg  {{ background: #ddd; border-radius: 6px; height: 20px; width: 300px; display:inline-block; }}
        .bar-fg  {{ background: #4caf50; border-radius: 6px; height: 20px; width: {pct:.1f}%; }}
        table  {{ border-collapse: collapse; width: 100%; margin-top: 1em; }}
        th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
        th     {{ background: #f0f0f0; }}
    </style>
    </head>
    <body>
    <h1>Coverage Report</h1>
    <div class="summary">
        <strong>File:</strong> {source_file}<br>
        <strong>Generated:</strong> {date_str}<br>
        <strong>Branches covered:</strong> {covered} / {total} ({pct:.1f}%)<br>
        <div class="bar-bg"><div class="bar-fg"></div></div>
    </div>
    <table>
        <thead>
        <tr>
            <th>ID</th><th>Line</th><th>Type</th><th>Label</th>
            <th>True hits</th><th>False hits</th><th>Covered</th>
        </tr>
        </thead>
        <tbody>
    {table_rows}    </tbody>
    </table>
    </body>
    </html>"""
    
    with open(output_path, "w") as f:
        f.write(html)
    print(f"✓ Wrote HTML to {output_path}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 report.py <branch_map.json> <coverage.json>")
        sys.exit(1)

    branch_map_path = sys.argv[1]
    coverage_path   = sys.argv[2]

    if not os.path.exists(branch_map_path):
        print(f"❌ Error: branch map not found: {branch_map_path}")
        sys.exit(1)

    branch_map  = load_branch_map(branch_map_path)
    coverage    = load_coverage(coverage_path)
    rows        = merge(branch_map, coverage)

    # Derive output paths from branch map path
    base        = branch_map_path.replace("_branch_map.json", "")
    source_file = os.path.basename(base).replace("_inst", ".c")
    csv_out     = base + "_report.csv"
    html_out    = base + "_report.html"

    write_csv(rows, csv_out, source_file)
    write_html(rows, html_out, source_file)

    total   = len(rows)
    covered = sum(1 for r in rows if r["covered"])
    pct     = (covered / total * 100) if total > 0 else 0
    print(f"\n📊 Coverage: {covered}/{total} branches ({pct:.1f}%)")

if __name__ == "__main__":
    main()