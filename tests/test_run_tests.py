"""src/run_tests.py: a wall-clock timeout keeps the coverage written before it, and a branch
map that is given but unusable is an error (exit 2).

The program is instrumented and compiled with the real runtime (cov_runtime.c); run_tests.py
is run as a subprocess, as c2obra.sh runs it.

Run from the repo root:  python3 -m unittest tests.test_run_tests -v
"""
import contextlib, io, json, os, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
sys.path.insert(0, SRC)
import instrument as I

# The if is taken (true edge), then the program spins in a loop that never ends
SPIN_C = r'''extern int __VERIFIER_nondet_int(void);
int main(void) {
    int x = __VERIFIER_nondet_int();
    if (x > 0) {
        volatile int spin = 1;
        while (spin) { }
    }
    return 0;
}
'''


def build(d, code, name='a'):
    """Instrument and compile code in d. Returns (binary, branch map path)."""
    c = os.path.join(d, f'{name}.c')
    with open(c, 'w') as f:
        f.write(code)
    inst = os.path.join(d, f'{name}_inst.c')
    with contextlib.redirect_stdout(io.StringIO()):
        I.instrument_file(c, inst, flags=[])
    exe = os.path.join(d, name)
    subprocess.run(['gcc', '-w', inst, os.path.join(SRC, 'cov_runtime.c'),
                    os.path.join(SRC, 'verifier_stubs.c'), '-I', SRC, '-o', exe], check=True)
    return exe, os.path.join(d, f'{name}_inst_branch_map.json')


def one_test_suite(d, value):
    suite = os.path.join(d, 'suite')
    os.makedirs(suite)
    with open(os.path.join(suite, 'test_input-1.xml'), 'w') as f:
        f.write(f'<testcase><input>{value}</input></testcase>')
    return suite


def run_tests(d, *args, timeout=120):
    return subprocess.run([sys.executable, os.path.join(SRC, 'run_tests.py'), *args],
                          cwd=d, capture_output=True, text=True, timeout=timeout)


class Timeout(unittest.TestCase):
    def test_timeout_keeps_partial_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            exe, bmap = build(d, SPIN_C)
            suite = one_test_suite(d, '5')
            t0 = time.monotonic()
            r = run_tests(d, exe, suite, bmap, '--cpu', '30', '--wall', '2')
            secs = time.monotonic() - t0
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('[test_input-1.xml] TIMED OUT after 2s', r.stdout)
            with open(os.path.join(d, 'output', 'coverage_report.json')) as f:
                summary = json.load(f)['summary']
            self.assertEqual(summary['test_run_statuses'],
                             {'pass': 0, 'partial': 1, 'timeout': 0, 'crash': 0})
            # if: true edge taken; while: true edge taken; neither false edge
            self.assertEqual((summary['covered_branches'], summary['total_branches_count']), (2, 4))
            self.assertLess(secs, 15)


class BranchMap(unittest.TestCase):
    """A branch map that is given but unusable stops run_tests.py with exit 2 before any test."""

    def fake_binary(self, d):
        """A 'test binary' that leaves a file behind, to show whether any test was run."""
        exe = os.path.join(d, 'bin.sh')
        with open(exe, 'w') as f:
            f.write(f"#!/bin/sh\ntouch '{os.path.join(d, 'ran')}'\n")
        os.chmod(exe, 0o755)
        return exe

    def check_error(self, d, bmap, words):
        r = run_tests(d, self.fake_binary(d), '-', bmap)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(f"❌ Error: branch map '{bmap}' {words}", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(d, 'ran')))
        self.assertFalse(os.path.exists(os.path.join(d, 'output')))

    def write(self, d, text):
        p = os.path.join(d, 'm.json')
        with open(p, 'w') as f:
            f.write(text)
        return p

    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.check_error(d, os.path.join(d, 'none.json'), 'not found')

    def test_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, 'dir.json'))                 # open() fails: a directory
            self.check_error(d, os.path.join(d, 'dir.json'), 'cannot be read')

    def test_malformed_json(self):
        with tempfile.TemporaryDirectory() as d:
            self.check_error(d, self.write(d, '{"branches": ['), 'is malformed JSON')

    def test_no_edges(self):
        with tempfile.TemporaryDirectory() as d:
            self.check_error(d, self.write(d, '{"branches": []}'), 'is not usable')
            self.check_error(d, self.write(d, '{"branches": [], "edges": {}}'), 'is not usable')
            self.check_error(d, self.write(d, '[]'), 'is not usable')

    def test_no_map_given_runs_as_before(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_tests(d, self.fake_binary(d), '-')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('No branch map — edge totals unavailable', r.stdout)
            self.assertTrue(os.path.exists(os.path.join(d, 'ran')))


if __name__ == '__main__':
    unittest.main()
