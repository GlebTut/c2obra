#!/usr/bin/env python3
import os, sys, glob, subprocess, json, resource, signal, argparse
import xml.etree.ElementTree as ET

# * Resource limits

CPU_TIME_LIMIT = 30     # Seconds per test run
MEMORY_LIMIT_MB = 512   # MB per test run
WALL_TIMEOUT = 35       # wall-clock timeout (slighty above CPU limit)

def set_resource_limits():
    """Called inside child process before exec - sets hard CPU + memory caps."""
    # CPU time: SIGKILL sent by kernel if exceeded
    resource.setrlimit(resource.RLIMIT_CPU,
                       (CPU_TIME_LIMIT, CPU_TIME_LIMIT))
    # Virtual memory: prevents memory bombs
    resource.setrlimit(resource.RLIMIT_AS,
                       (MEMORY_LIMIT_MB * 1024 * 1024,
                        MEMORY_LIMIT_MB * 1024 * 1024))
    

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

def run_test(binary, inputs, test_name):
    """Run binary with given inputs. Returns coverage dict."""
    with open("test_input.txt", "w") as f:
        f.write("\n".join(inputs))

    timed_out = False
    killed = False
    
    try:
        result = subprocess.run(
            [binary], 
            capture_output=True, 
            text=True,
            timeout=WALL_TIMEOUT,           # Wall-clock hard stop
            preexec_fn=set_resource_limits  # CPU + memory caps in child
        )
        
        exit_code = result.returncode
    
    except subprocess.TimeoutExpired as e:
        # Kill entire process group to prevent zombies
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

    # Read coverage written by destructor in cov_runtime.c
    try:
        with open("coverage.json") as f:
            coverage = json.load(f)
        os.remove("coverage.json")
    except FileNotFoundError:
        print(f"  ⚠️  [{test_name}] No coverage.json written — binary may have crashed")
        coverage = {"branches": []}
    except json.JSONDecodeError:
        print(f"  ⚠️  [{test_name}] coverage.json is malformed")
        coverage = {"branches": []}
        
    if not timed_out and not killed:
        print(f"\n=== {test_name} ===")
        print(f"  Inputs:    {inputs}")
        print(f"  Exit code: {exit_code}")
        print(f"  Branches hit: {len(coverage.get('branches', []))}")

    return coverage

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

def print_summary(merged, branch_map=None):
    if branch_map is None:
        branch_map = {}
        
    print("\n" + "="*65)
    print("AGGREGATED COVERAGE SUMMARY")
    print("="*65)
    print(f"{'ID':<6} {'Line':<8} {'Type':<18} {'True':>6} {'False':>7} {'Status':>10}")
    print("-"*65)

    total = len(merged)
    fully_covered = 0
    report_branches = []

    for bid in sorted(merged.keys()):
        b = merged[bid]
        meta = branch_map.get(bid, {})
        line  = meta.get('line', '?')
        btype = meta.get('type', '?').replace('_statement', '').replace('_', '-')
        t = "✅" if b["true"]  > 0 else "❌"
        f = "✅" if b["false"] > 0 else "❌"
        covered = b["true"] > 0 and b["false"] > 0
        if covered:
            fully_covered += 1
        status = "FULL" if covered else "PARTIAL"
        print(f"{bid:<6} {str(line):<8} {btype:<18} {t:>6} {f:>7} {status:>10}")
        report_branches.append({
            "id": bid,
            "line": line,
            "type": meta.get("type", "?"),
            "true": b["true"],
            "false": b["false"],
            "covered": covered
        })

    print("-"*65)
    pct = (fully_covered / total * 100) if total > 0 else 0
    print(f"Fully covered: {fully_covered}/{total} branches")
    print(f"Branch coverage: {pct:.1f}%")
    print(f"\nResource limits applied: CPU={CPU_TIME_LIMIT}s  MEM={MEMORY_LIMIT_MB}MB  WALL={WALL_TIMEOUT}s")

    report = {
        "summary": {
            "total_branches": total,
            "covered_branches": fully_covered,
            "branch_coverage_pct": round(pct, 1),
            "resource_limits": {
                "cpu_seconds":  CPU_TIME_LIMIT,
                "memory_mb":    MEMORY_LIMIT_MB,
                "wall_timeout": WALL_TIMEOUT
            }
        },
        "branches": report_branches
    }
    with open("coverage_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report written to coverage_report.json")

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

    # Override module-level constants with CLI values
    CPU_TIME_LIMIT  = args.cpu
    MEMORY_LIMIT_MB = args.memory
    WALL_TIMEOUT    = args.wall if args.wall else args.cpu + 5

    branch_map    = load_branch_map(args.branch_map) if args.branch_map else {}
    all_coverages = []

    if not os.path.exists(args.binary):
        print(f"❌ Error: Binary '{args.binary}' not found — did compilation succeed?")
        sys.exit(1)
    if not os.access(args.binary, os.X_OK):
        print(f"❌ Error: Binary '{args.binary}' is not executable")
        sys.exit(1)

    if args.suite_dir != "-":
        xml_files = sorted(glob.glob(f"{args.suite_dir}/test_input-*.xml"))
        print(f"Found {len(xml_files)} test cases")
        if not xml_files:                                          # ← add this
            print("⚠️  Warning: No XML test cases found in suite — running with no inputs")
            cov = run_test(args.binary, [], "no_inputs")
            all_coverages.append(cov)
        else:
            for xml_file in xml_files:
                inputs = parse_inputs(xml_file)
                cov    = run_test(args.binary, inputs, os.path.basename(xml_file))
                all_coverages.append(cov)
    else:
        print("No test-suite provided — running binary once with no inputs")
        cov = run_test(args.binary, [], "no_inputs")
        all_coverages.append(cov)

    merged = merge_coverage(all_coverages)
    if not merged:
        print("⚠️  Warning: No coverage data collected — all runs may have crashed")
    print_summary(merged, branch_map)
