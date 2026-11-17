#!/usr/bin/env python3
"""C²oBra report: CSV output (edge mode and --mode testcov)."""

import csv, os, sys


def write_csv(rows, totals, output_path, source_file):
    """totals: (covered edges, total edges) from edges.edge_coverage()."""
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
            covered_edges, total_edges = totals
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


def write_testcov_csv(branch_map_data, coverage, csv_path):
    """--mode testcov: one CSV row per TestCov goal and a SUMMARY row; totals printed."""
    import testcov_goals as G
    try:
        r = G.goals(branch_map_data, coverage)
    except G.MissingGoalFactsError as e:
        print(f"\u274c Error: {e}")
        sys.exit(1)
    pct = r["covered"] / r["total"] * 100 if r["total"] else 0.0
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["goal", "line", "kind", "decision_id", "reached"])
        for i, g in enumerate(r["goals"], 1):
            w.writerow([i, g["line"], g["kind"], g["id"], "yes" if g["reached"] else "no"])
        w.writerow(["SUMMARY", "", "", "", f"{r['covered']}/{r['total']} goals ({pct:.1f}%)"])
    print(f"TestCov goals: {r['covered']}/{r['total']} ({pct:.1f}%)  [--mode testcov]")
    print(f"\u2713 Wrote {csv_path}")
