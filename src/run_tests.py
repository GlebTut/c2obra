#!/usr/bin/env python3
import os, sys, glob, subprocess, json, resource, signal, argparse, tempfile, shutil
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed



# * Resource limits


CPU_TIME_LIMIT = 30     # Seconds per test run
MEMORY_LIMIT_MB = 512   # MB per test run
WALL_TIMEOUT = 35       # wall-clock timeout (slightly above CPU limit)



def set_resource_limits():
    soft = max(1, CPU_TIME_LIMIT - 1)
    hard = CPU_TIME_LIMIT
    resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))



# * XML test input parsing


def parse_inputs(xml_file):
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        return [inp.text.strip() for inp in root.findall('input') if inp.text]
    except ET.ParseError as e:
        print(f"⚠️  Warning: Could not parse '{xml_file}': {e} — skipping")
        return []



# * Single test execution


def run_test(binary, inputs, test_name, work_dir):
    """Run binary with given inputs. Returns (coverage, inputs, test_name, status)."""
    input_file = os.path.join(work_dir, "test_input.txt")
    cov_file   = os.path.join(work_dir, "coverage.json")

    with open(input_file, "w") as f:
        f.write("\n".join(inputs))

    env = os.environ.copy()
    env["COVERAGE_OUTPUT"] = cov_file

    timed_out = False
    killed    = False

    try:
        result = subprocess.run(
            [binary],
            capture_output=True,
            text=True,
            timeout=WALL_TIMEOUT,
            preexec_fn=set_resource_limits,
            cwd=work_dir,
            env=env
        )
        exit_code = result.returncode

    except subprocess.TimeoutExpired as e:
        try:
            os.killpg(os.getpgid(e.process.pid), signal.SIGKILL)
        except Exception:
            pass
        timed_out = True
        exit_code = -1
        print(f"  ⚠️  [{test_name}] TIMED OUT after {WALL_TIMEOUT}s — killed")

    except Exception as e:
        killed    = True
        exit_code = -1
        print(f"  ⚠️  [{test_name}] ERROR: {e}")

    try:
        with open(cov_file) as f:
            coverage = json.load(f)
    except FileNotFoundError:
        print(f"  ⚠️  [{test_name}] No coverage.json written — binary may have crashed")
        coverage = {"branches": []}
    except json.JSONDecodeError:
        print(f"  ⚠️  [{test_name}] coverage.json is malformed")
        coverage = {"branches": []}

    if not timed_out and not killed:
        print(f"\n=== {test_name} ===")
        print(f"  Inputs:       {inputs}")
        print(f"  Exit code:    {exit_code}")
        print(f"  Branches hit: {len(coverage.get('branches', []))}")

    if timed_out:
        status = "timeout"
    elif exit_code != 0 and len(coverage.get("branches", [])) > 0:
        status = "partial"
    elif exit_code != 0:
        status = "crash"
    else:
        status = "pass"

    return coverage, inputs, test_name, status



# * Coverage merging


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



# * Branch map loader


def load_branch_map(map_file):
    try:
        with open(map_file) as f:
            data = json.load(f)
        return {b['id']: b for b in data['branches']}
    except FileNotFoundError:
        print(f"⚠️  Branch map '{map_file}' not found — running without metadata")
        return {}
    except json.JSONDecodeError:
        print(f"⚠️  Branch map '{map_file}' is malformed JSON")
        return {}



# * Summary + report writer


def print_summary(merged, branch_map=None, test_inputs_log=None):
    if branch_map is None:
        branch_map = {}
    if test_inputs_log is None:
        test_inputs_log = []

    print("\n" + "="*65)
    print("AGGREGATED COVERAGE SUMMARY")
    print("="*65)
    print(f"{'ID':<6} {'Line':<8} {'Type':<18} {'True':>6} {'False':>7} {'Status':>10}")
    print("-"*65)

    all_ids       = sorted(set(list(branch_map.keys()) + list(merged.keys())))
    total         = len(branch_map) if branch_map else len(merged)
    total_edges   = total * 2
    covered_true  = 0
    covered_false = 0
    report_branches = []

    for bid in all_ids:
        b     = merged.get(bid, {"true": 0, "false": 0})
        meta  = branch_map.get(bid, {})
        line  = meta.get('line', '?')
        btype = meta.get('type', '?').replace('_statement', '').replace('_', '-')
        t_hit = b["true"]  > 0
        f_hit = b["false"] > 0
        if t_hit: covered_true  += 1
        if f_hit: covered_false += 1
        t = "✅" if t_hit else "❌"
        f = "✅" if f_hit else "❌"
        covered = t_hit and f_hit
        if covered:
            branch_status = "FULL"
        elif t_hit or f_hit:
            branch_status = "PARTIAL"
        else:
            branch_status = "NONE"
        print(f"{bid:<6} {str(line):<8} {btype:<18} {t:>6} {f:>7} {branch_status:>10}")
        report_branches.append({
            "id":      bid,
            "line":    line,
            "type":    meta.get("type", "?"),
            "true":    b["true"],
            "false":   b["false"],
            "covered": covered
        })

    print("-"*65)
    covered_edges = covered_true + covered_false
    pct = (covered_edges / total_edges * 100) if total_edges > 0 else 0
    print(f"Covered branches: {covered_edges}/{total_edges}  ({covered_true} true, {covered_false} false)")
    print(f"Branch coverage: {pct:.1f}%")
    print(f"\nResource limits applied: CPU={CPU_TIME_LIMIT}s  MEM={MEMORY_LIMIT_MB}MB  WALL={WALL_TIMEOUT}s")

    # Count test run statuses
    status_counts = {"pass": 0, "partial": 0, "timeout": 0, "crash": 0}
    for t in test_inputs_log:
        s = t.get("status", "pass")
        status_counts[s] = status_counts.get(s, 0) + 1

    if any(v > 0 for v in status_counts.values()):
        print(f"Test run statuses: " + "  ".join(
            f"{k.upper()}={v}" for k, v in status_counts.items() if v > 0
        ))

    report = {
        "summary": {
            "total_branches":       total,
            "total_branches_count": total_edges,
            "covered_branches":     covered_edges,
            "branch_coverage_pct":  round(pct, 1),
            "coverage_pct":         round(pct, 1),   # alias used by report.py / merge_reports.py
            "test_run_statuses":    status_counts,
            "resource_limits": {
                "cpu_seconds":  CPU_TIME_LIMIT,
                "memory_mb":    MEMORY_LIMIT_MB,
                "wall_timeout": WALL_TIMEOUT
            }
        },
        "branches":  report_branches,
        "test_runs": test_inputs_log
    }

    os.makedirs("output", exist_ok=True)
    with open("output/coverage_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report written to output/coverage_report.json")



# * Entry point


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run tests and measure branch coverage"
    )
    parser.add_argument("binary",                help="Path to instrumented binary")
    parser.add_argument("suite_dir",  nargs="?", help="Test suite directory (or - for no inputs)", default="-")
    parser.add_argument("branch_map", nargs="?", help="Path to branch_map.json", default=None)
    parser.add_argument("--cpu",    type=int,    help="CPU time limit in seconds (default: 30)",  default=30)
    parser.add_argument("--memory", type=int,    help="Memory limit in MB (default: 512)",        default=512)
    parser.add_argument("--wall",   type=int,    help="Wall timeout in seconds (default: cpu+5)", default=None)
    args = parser.parse_args()

    args.binary = os.path.abspath(args.binary)

    CPU_TIME_LIMIT  = args.cpu
    MEMORY_LIMIT_MB = args.memory
    WALL_TIMEOUT    = args.wall if args.wall else args.cpu + 5

    branch_map      = load_branch_map(args.branch_map) if args.branch_map else {}
    all_coverages   = []
    test_inputs_log = []

    if not os.path.exists(args.binary):
        print(f"❌ Error: Binary '{args.binary}' not found — did compilation succeed?")
        sys.exit(1)
    if not os.access(args.binary, os.X_OK):
        print(f"❌ Error: Binary '{args.binary}' is not executable")
        sys.exit(1)

    workers   = max(1, os.cpu_count() - 1)
    work_dirs = []

    if args.suite_dir != "-":
        xml_files = sorted(glob.glob(f"{args.suite_dir}/test_input-*.xml"))
        print(f"Found {len(xml_files)} test cases — running with {workers} workers")
        if not xml_files:
            print("⚠️ Warning: No XML test cases found in suite — running with no inputs")
            work_dir = tempfile.mkdtemp(prefix="cov_")
            work_dirs.append(work_dir)
            cov, inputs, tname, status = run_test(args.binary, [], "no_inputs", work_dir)
            all_coverages.append(cov)
            test_inputs_log.append({"test_case": tname, "inputs": inputs, "status": status})
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}
                for xml_file in xml_files:
                    work_dir = tempfile.mkdtemp(prefix="cov_")
                    work_dirs.append(work_dir)
                    inputs = parse_inputs(xml_file)
                    f = executor.submit(
                        run_test, args.binary, inputs,
                        os.path.basename(xml_file), work_dir
                    )
                    futures[f] = xml_file
                for future in as_completed(futures):
                    cov, inputs, tname, status = future.result()
                    all_coverages.append(cov)
                    test_inputs_log.append({"test_case": tname, "inputs": inputs, "status": status})
    else:
        print("No test-suite provided — running binary once with no inputs")
        work_dir = tempfile.mkdtemp(prefix="cov_")
        work_dirs.append(work_dir)
        cov, inputs, tname, status = run_test(args.binary, [], "no_inputs", work_dir)
        all_coverages.append(cov)
        test_inputs_log.append({"test_case": tname, "inputs": inputs, "status": status})

    for d in work_dirs:
        shutil.rmtree(d, ignore_errors=True)

    merged = merge_coverage(all_coverages)
    if not merged:
        print("⚠️  Warning: No coverage data collected — all runs may have crashed")
    os.makedirs("output", exist_ok=True)
    with open("output/test_inputs_log.json", "w") as f:
        json.dump(test_inputs_log, f, indent=2)
    print("✓ Test inputs log written to output/test_inputs_log.json")
    print_summary(merged, branch_map, test_inputs_log)