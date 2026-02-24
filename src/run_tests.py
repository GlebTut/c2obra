#!/usr/bin/env python3
import os, sys, glob, subprocess, json

def parse_inputs(xml_file):
    import xml.etree.ElementTree as ET
    tree = ET.parse(xml_file)
    root = tree.getroot()
    return [inp.text.strip() for inp in root.findall('input')]

def run_test(binary, inputs, test_name):
    with open("test_input.txt", "w") as f:
        f.write("\n".join(inputs))

    result = subprocess.run([binary], capture_output=True, text=True)

    try:
        with open("coverage.json") as f:
            coverage = json.load(f)
    except:
        coverage = {"branches": []}

    print(f"\n=== {test_name} ===")
    print(f"Inputs: {inputs}")
    print(f"Exit code: {result.returncode}")
    print(f"Coverage: {json.dumps(coverage, indent=2)}")

    return coverage

def merge_coverage(all_coverages):
    merged = {}
    for cov in all_coverages:
        for branch in cov.get("branches", []):
            bid = branch["id"]
            if bid not in merged:
                merged[bid] = {"id": bid, "true": 0, "false": 0}
            merged[bid]["true"]  += branch["true"]
            merged[bid]["false"] += branch["false"]
    return merged

def load_branch_map(map_file):
    """Load branch map JSON"""
    try:
        with open(map_file) as f:
            data = json.load(f)
            return {b['id']: b for b in data['branches']}
    except:
        return {}

def print_summary(merged, branch_map={}):
    print("\n" + "="*65)
    print("AGGREGATED COVERAGE SUMMARY")
    print("="*65)
    print(f"{'ID':<6} {'Line':<8} {'Type':<18} {'True':>6} {'False':>7} {'Status':>10}")
    print("-"*65)

    total = len(merged)
    fully_covered = 0

    for bid in sorted(merged.keys()):
        b = merged[bid]
        meta = branch_map.get(bid, {})
        line = meta.get('line', '?')
        btype = meta.get('type', '?').replace('_statement', '').replace('_', '-')
        t = "✅" if b["true"]  > 0 else "❌"
        f = "✅" if b["false"] > 0 else "❌"
        covered = b["true"] > 0 and b["false"] > 0
        if covered:
            fully_covered += 1
        status = "FULL" if covered else "PARTIAL"
        print(f"{bid:<6} {str(line):<8} {btype:<18} {t:>6} {f:>7} {status:>10}")

    print("-"*65)
    print(f"Fully covered: {fully_covered}/{total} branches")
    pct = (fully_covered / total * 100) if total > 0 else 0
    print(f"Branch coverage: {pct:.1f}%")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 src/run_tests.py <binary> <test-suite-dir> [branch_map.json]")
        sys.exit(1)

    binary    = sys.argv[1]
    suite_dir = sys.argv[2]
    map_file  = sys.argv[3] if len(sys.argv) > 3 else None      # ← ADD THIS

    branch_map = load_branch_map(map_file) if map_file else {}   # ← ADD THIS

    xml_files = sorted(glob.glob(f"{suite_dir}/test_input-*.xml"))
    print(f"Found {len(xml_files)} test cases")

    all_coverages = []
    for xml_file in xml_files:
        inputs = parse_inputs(xml_file)
        cov = run_test(binary, inputs, os.path.basename(xml_file))
        all_coverages.append(cov)

    merged = merge_coverage(all_coverages)
    print_summary(merged, branch_map)
