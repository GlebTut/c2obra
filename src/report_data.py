#!/usr/bin/env python3
"""C²oBra report: load branch map / coverage / test inputs and merge them into rows."""

import json, os, sys
import edges as E


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
    """One row per branch-map entry. Status comes from the map's edges (edges.py), not from
    true && false: a switch label has only its true edge."""
    status = E.row_status(branch_map_data, coverage)
    sides  = E.sides_by_id(branch_map_data)
    rows = []
    for b in branch_map_data.get("branches", []):
        bid         = b["id"]
        hits        = coverage.get(int(bid), {})
        true_count  = hits.get("true",  0)
        false_count = hits.get("false", 0)
        edges_hit, edges_total = status.get(int(bid), (0, 0))
        row_state   = E.status_label(edges_hit, edges_total)
        rows.append({
            "branch_id":   bid,
            "line":        b.get("line",  "?"),
            "type":        b.get("type",  "?"),
            "label":       b.get("label", ""),
            "true_label":  b.get("true_label",  ""),
            "false_label": b.get("false_label", ""),
            "true_count":  true_count,
            "false_count": false_count,
            "true_edge":   "true"  in sides.get(int(bid), ()),
            "false_edge":  "false" in sides.get(int(bid), ()),
            "edges_hit":   edges_hit,
            "edges_total": edges_total,
            "status":      row_state,
            "covered":     row_state == "FULL",
        })
    return rows
