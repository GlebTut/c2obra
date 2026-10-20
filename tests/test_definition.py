"""The branch definition: tests/definition/d01-d15 with hand-derived expected edges.

tests/definition/expected.csv is the spec (one row per program: total_edges, covered_edges,
derived by hand from the comments in each file). Each program is instrumented, compiled with
the runtime, run once (main() calls the code with fixed arguments; no inputs), and the edge
counts from edges.edge_coverage() are compared with the CSV. The instrumented program must
also behave like the original (same stdout and exit code; d13 exits with 1).

A second test checks that every place that reports a total (run_tests.py summary JSON,
report.py CSV and HTML, merge_reports.py) gives the same numbers as edges.edge_coverage().

Run from the repo root:  python3 -m unittest discover -s tests -p "test_*.py" -v
"""
import contextlib, csv, io, json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
DEFS = os.path.join(HERE, 'definition')
sys.path.insert(0, SRC)
import instrument as I
import edges as E
import merge_reports
import run_tests


def expected_rows():
    with open(os.path.join(DEFS, 'expected.csv')) as f:
        return list(csv.DictReader(f))


def build_and_run(d, c_file, extra=()):
    """(exit code, stdout). Exit code is not checked here: d13 exits with 1 on purpose."""
    exe = c_file[:-2]
    r = subprocess.run(['gcc', '-w', '-o', exe, c_file, *extra, '-I', SRC], capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(f"gcc failed on {os.path.basename(c_file)}:\n{r.stderr}")
    env = dict(os.environ, COVERAGE_OUTPUT=os.path.join(d, 'coverage.json'))
    r = subprocess.run([exe], capture_output=True, text=True, cwd=d, env=env, timeout=30)
    return r.returncode, r.stdout


def instrument_and_run(d, name):
    """Instrument tests/definition/<name> into d, run original and instrumented.
    Returns (branch map, coverage {id: {"true", "false"}}, original run, instrumented run)."""
    orig = os.path.join(d, name)
    shutil.copy(os.path.join(DEFS, name), orig)
    inst = os.path.join(d, name[:-2] + '_inst.c')
    with contextlib.redirect_stdout(io.StringIO()):
        I.instrument_file(orig, inst, flags=[])
    with open(inst[:-2] + '_branch_map.json') as f:
        branch_map = json.load(f)
    orig_run = build_and_run(d, orig)
    inst_run = build_and_run(d, inst, [os.path.join(SRC, 'cov_runtime.c'), os.path.join(SRC, 'verifier_stubs.c')])
    with open(os.path.join(d, 'coverage.json')) as f:
        coverage = {b['id']: b for b in json.load(f)['branches']}
    return branch_map, coverage, orig_run, inst_run


class DefinitionPrograms(unittest.TestCase):
    def test_edges_match_expected_csv(self):
        for row in expected_rows():
            with self.subTest(file=row['file']), tempfile.TemporaryDirectory() as d:
                branch_map, coverage, orig_run, inst_run = instrument_and_run(d, row['file'])
                self.assertEqual(inst_run, orig_run, "instrumented program behaves differently")
                self.assertEqual(E.edge_coverage(branch_map, coverage),
                                 (int(row['covered_edges']), int(row['total_edges'])))

    def test_switch_side_effect_exit_code(self):
        # d13: switch (i++) must evaluate i++ once, so the program still returns 1
        with tempfile.TemporaryDirectory() as d:
            _, _, orig_run, inst_run = instrument_and_run(d, 'd13_switch_side_effect.c')
        self.assertEqual(orig_run[0], 1)
        self.assertEqual(inst_run[0], 1)


class AllReportsAgree(unittest.TestCase):
    """run_tests.py, report.py and merge_reports.py must report edge_coverage()'s numbers.
    d10 (switch without default) is the case where the old len(rows) * 2 gave 3/6, not 2/3."""

    NAME = 'd10_switch_no_default.c'

    def test_same_totals_everywhere(self):
        with tempfile.TemporaryDirectory() as d:
            branch_map, coverage, _, _ = instrument_and_run(d, self.NAME)
            covered, total = E.edge_coverage(branch_map, coverage)
            self.assertEqual((covered, total), (2, 3))

            # run_tests.print_summary writes output/coverage_report.json relative to the cwd
            cwd = os.getcwd()
            os.chdir(d)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    run_tests.print_summary(coverage, branch_map, [])
            finally:
                os.chdir(cwd)
            with open(os.path.join(d, 'output', 'coverage_report.json')) as f:
                summary = json.load(f)['summary']
            self.assertEqual((summary['covered_branches'], summary['total_branches_count']), (covered, total))

            # report.py as c2obra.sh runs it: CSV SUMMARY row and HTML header
            base = os.path.join(d, self.NAME[:-2] + '_inst')
            cov_file = base + '_coverage.json'
            shutil.copy(os.path.join(d, 'output', 'coverage_report.json'), cov_file)
            subprocess.run([sys.executable, os.path.join(SRC, 'report.py'), base + '_branch_map.json', cov_file,
                            '--output', base + '_report.html', '--csv', base + '_report.csv', '--no-summary'],
                           capture_output=True, text=True, check=True)
            with open(base + '_report.csv') as f:
                last = list(csv.DictReader(f))[-1]
            self.assertIn(f"({covered}/{total} branches)", last['covered'])
            with open(base + '_report.html') as f:
                self.assertIn(f"{covered}/{total} branches", f.read())

            # merge_reports.py: per-file stats of the summary page
            self.assertEqual(merge_reports.compute_stats(branch_map, coverage)[:2], (total, covered))


if __name__ == '__main__':
    unittest.main()
