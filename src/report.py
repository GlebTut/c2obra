#!/usr/bin/env python3
"""
C²oBra - Report Generator
Reads branch_map.json + coverage.json and outputs HTML + CSV + source HTML reports.

The work is split over report_data.py (load + merge), report_csv.py, report_source.py and
report_html.py (CSS/JS in report_assets/); this file is only the command line.
"""

import os, sys

import edges as E
from report_data import load_branch_map, load_coverage, load_test_inputs, merge
from report_csv import write_csv, write_testcov_csv
from report_source import write_source_html
from report_html import write_html


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
    parser.add_argument("--mode", choices=["edges", "testcov"], default="edges",
                        help="edges (default): C\u00b2oBra's edge definition. testcov: count TestCov's "
                             "goals from the same counters (docs/testcov_mode.md); writes only --csv")
    parser.add_argument("--source", help="no longer needed: --mode testcov reads the branch map only")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    branch_map_data = load_branch_map(args.branch_map)
    coverage        = load_coverage(args.coverage)
    if args.mode == "testcov":
        return write_testcov_csv(branch_map_data, coverage, args.csv)
    test_inputs     = load_test_inputs(args.test_inputs)
    try:
        rows   = merge(branch_map_data, coverage)
        totals = E.edge_coverage(branch_map_data, coverage)
    except E.MissingEdgesError as e:
        print(f"❌ Error: {args.branch_map}: {e}")
        sys.exit(1)

    source_file      = branch_map_data.get("source_file", "unknown")
    base             = os.path.splitext(args.output)[0]
    source_html_path = base.removesuffix("_report") + "_source.html"
    source_html_name = os.path.basename(source_html_path)

    wrote_source = write_source_html(rows, branch_map_data, source_html_path, os.path.basename(args.output))

    write_html(rows, totals, args.output, source_file,
               source_html_name=source_html_name if wrote_source else None,
               test_inputs=test_inputs,
               no_summary=args.no_summary)
    write_csv(rows, totals, args.csv, source_file)


if __name__ == "__main__":
    main()
