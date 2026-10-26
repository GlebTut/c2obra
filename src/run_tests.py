#!/usr/bin/env python3
import os, sys, glob, subprocess, json, resource, signal, argparse, tempfile, shutil
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import edges as E




# * Resource limits



CPU_TIME_LIMIT  = 30    # Seconds per test run
MEMORY_LIMIT_MB = 512   # MB per test run
WALL_TIMEOUT    = 35    # wall-clock timeout (slightly above CPU limit)




def set_resource_limits():
    soft = max(1, CPU_TIME_LIMIT - 1)
    hard = CPU_TIME_LIMIT
    resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))
    mem_bytes = MEMORY_LIMIT_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))




# * XML test input parsing



def parse_inputs(xml_file):
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        for elem in root.iter():
            elem.tag = elem.tag.split('}', 1)[-1] if '}' in elem.tag else elem.tag
        return [inp.text.strip() for inp in root.findall('.//input') if inp.text]
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
    crashed   = False

    try:
        # Popen, not subprocess.run: run() SIGKILLs the child itself on timeout, so the SIGTERM
        # below never arrived and cov_runtime.c wrote no coverage. start_new_session gives the
        # test its own process group, so killpg() signals the test and not run_tests.py.
        with subprocess.Popen(
            [binary],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=set_resource_limits,
            cwd=work_dir,
            env=env,
            start_new_session=True
        ) as proc:
            try:
                proc.communicate(timeout=WALL_TIMEOUT)
            except subprocess.TimeoutExpired:
                # Stage 1: SIGTERM → triggers dump_coverage() in cov_runtime.c
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.communicate(timeout=3)             # wait for coverage flush
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)     # force kill if still alive
                    proc.communicate()
                except ProcessLookupError:
                    pass                                    # exited just before the SIGTERM
            except BaseException:
                proc.kill()
                raise
        exit_code = -1 if timed_out else proc.returncode
        if timed_out:
            print(f"  ⚠️  [{test_name}] TIMED OUT after {WALL_TIMEOUT}s — killed")
        elif exit_code < 0:
            crashed = True
            # cov_runtime.c re-raises SIGSEGV/SIGABRT/SIGFPE after dumping, so the signal is
            # visible here; SIGXCPU/SIGTERM end with _exit(1) and are not seen as signals.
            try:
                sig = signal.Signals(-exit_code).name
            except ValueError:
                sig = f"signal {-exit_code}"
            print(f"  ⚠️  [{test_name}] ended by {sig} (exit code {exit_code})")

    except Exception as e:
        crashed   = True
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

    if not timed_out and not crashed:
        print(f"\n=== {test_name} ===")
        print(f"  Inputs:       {inputs}")
        print(f"  Exit code:    {exit_code}")
        print(f"  Branches hit: {len(coverage.get('branches', []))}")

    if timed_out:
        branches = coverage.get("branches", [])
        status = "partial" if branches else "timeout"
    elif crashed:
        branches = coverage.get("branches", [])
        status = "partial" if branches else "crash"
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
    """The whole map ({"branches": [...], "edges": [...]}). A map that was given but is missing,
    unreadable, not JSON or has no "edges" list stops the run with exit code 2: without it the
    edge total would silently become the number of hit branches."""
    try:
        with open(map_file) as f:
            data = json.load(f)
    except FileNotFoundError:
        problem = "not found"
    except json.JSONDecodeError as e:
        problem = f"is malformed JSON ({e})"
    except (OSError, ValueError) as e:
        problem = f"cannot be read ({e})"
    else:
        try:
            if not isinstance(data, dict) or not isinstance(E.map_edges(data), list):
                raise E.MissingEdgesError('branch map has no "edges" list')
            return data
        except E.MissingEdgesError as e:
            problem = f"is not usable: {e}"
    print(f"❌ Error: branch map '{map_file}' {problem}")
    sys.exit(2)




# * Summary + report writer



def print_summary(merged, map_data=None, test_inputs_log=None):
    """map_data: the loaded branch map (with "edges"); None/{} = no map, edge totals unknown."""
    map_data   = map_data or {}
    branch_map = {b['id']: b for b in map_data.get('branches', [])}
    if test_inputs_log is None:
        test_inputs_log = []

    print("\n" + "="*65)
    print("AGGREGATED COVERAGE SUMMARY")
    print("="*65)
    print(f"{'ID':<6} {'Line':<8} {'Type':<18} {'True':>6} {'False':>7} {'Status':>10}")
    print("-"*65)

    all_ids       = sorted(set(list(branch_map.keys()) + list(merged.keys())))
    total         = len(branch_map) if branch_map else len(merged)
    # Edges: the shared definition in edges.py (a switch label has 1 edge, a decision 2)
    if map_data:
        covered_edges, total_edges = E.edge_coverage(map_data, merged)
        rows = E.row_status(map_data, merged)
    else:
        print("⚠️  No branch map — edge totals unavailable")
        covered_edges, total_edges, rows = 0, 0, {}
    sides = E.sides_by_id(map_data) if map_data else {}
    report_branches = []

    for bid in all_ids:
        b     = merged.get(bid, {"true": 0, "false": 0})
        meta  = branch_map.get(bid, {})
        line  = meta.get('line', '?')
        btype = meta.get('type', '?').replace('_statement', '').replace('_', '-')
        t_hit = b["true"]  > 0
        f_hit = b["false"] > 0
        # "—": this counter side is not an edge (a switch label's false side)
        t = "—" if bid in sides and "true"  not in sides[bid] else ("✅" if t_hit else "❌")
        f = "—" if bid in sides and "false" not in sides[bid] else ("✅" if f_hit else "❌")
        hit, n = rows.get(bid, (0, 0))
        branch_status = E.status_label(hit, n)
        covered = branch_status == "FULL"
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
    pct = (covered_edges / total_edges * 100) if total_edges > 0 else 0
    print(f"Covered branches: {covered_edges}/{total_edges} edges")
    print(f"Branch coverage:  {pct:.1f}%")
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
            "coverage_pct":         round(pct, 1),
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
    print(f"\n✓ Full report written to output/coverage_report.json")




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
            print("⚠️  Warning: No XML test cases found in suite — running with no inputs")
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
        NO_INPUT_PROBES = [
            ("probe_pos",  ["2"]),    # positive, even
            ("probe_neg",  ["-1"]),   # negative, odd
            ("probe_zero", ["0"]),    # zero, even
        ]
        print(f"No test-suite provided — running {len(NO_INPUT_PROBES)} probes to maximise coverage")
        for tname, probe_inputs in NO_INPUT_PROBES:
            work_dir = tempfile.mkdtemp(prefix="cov_")
            work_dirs.append(work_dir)
            cov, inputs, name, status = run_test(args.binary, probe_inputs, tname, work_dir)
            all_coverages.append(cov)
            test_inputs_log.append({"test_case": name, "inputs": inputs, "status": status})
            
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
