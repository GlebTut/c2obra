"""Minimal reproductions for docs/failure_catalogue.md (phase 2): T2, R1, R2, R3, W3b.

An open issue is a test of the CORRECT behaviour marked @unittest.expectedFailure: it passes
while the bug is there, and reports an unexpected success (the run is then not successful)
once the bug is fixed, so the catalogue row must be updated.

Run from the repo root:  python3 -m unittest tests.test_failure_repro -v
"""
import contextlib, io, json, os, resource, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)
import instrument as I
from test_definition import build_and_run
from test_run_tests import SPIN_C, build, one_test_suite, run_tests

RUNTIME = [os.path.join(SRC, 'cov_runtime.c'), os.path.join(SRC, 'verifier_stubs.c')]


def instrument(d, name, code):
    """Write code to d/name and instrument it. Returns (original, instrumented, instrument.py stdout)."""
    orig = os.path.join(d, name)
    with open(orig, 'w') as f:
        f.write(code)
    inst = orig[:-2] + '_inst.c'
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        I.instrument_file(orig, inst, flags=[])
    return orig, inst, out.getvalue()


class T2CpuLimit(unittest.TestCase):
    @unittest.expectedFailure
    def test_cpu_limit_exit_is_not_a_pass(self):
        """RLIMIT_CPU soft limit (cpu - 1 = 1 s) -> SIGXCPU -> cov_runtime.c dumps and _exit(1);
        run_tests.py sees exit code 1, not a signal, and reports the run as a pass."""
        with tempfile.TemporaryDirectory() as d:
            exe, bmap = build(d, SPIN_C)
            r = run_tests(d, exe, one_test_suite(d, '5'), bmap, '--cpu', '2', '--wall', '30')
            with open(os.path.join(d, 'output', 'coverage_report.json')) as f:
                statuses = json.load(f)['summary']['test_run_statuses']
            self.assertEqual(statuses['pass'], 0, r.stdout)


R2_C = r'''#include <stdio.h>
int main(void) {
    int a = 3, n = 0, r = 0;
    if (a > 5) r += 1;
    if (n++ >= 0) r += 10;
    printf("r=%d n=%d\n", r, n);
    return 0;
}
'''


class R2OutOfRangeId(unittest.TestCase):
    @unittest.expectedFailure
    def test_out_of_range_id_keeps_behaviour(self):
        """MAX_BRANCHES=2 holds id 1 only. cover() for id 2 returns 0 without evaluating
        n++ >= 0: the original prints r=10 n=1, the instrumented copy r=0 n=0."""
        with tempfile.TemporaryDirectory() as d:
            orig, inst, _ = instrument(d, 'r2.c', R2_C)
            expected = build_and_run(d, orig)
            got = build_and_run(d, inst, RUNTIME + ['-DMAX_BRANCHES=2'])
            self.assertEqual(expected, (0, 'r=10 n=1\n'))
            self.assertEqual(got, expected)


class R3BranchCounters(unittest.TestCase):
    def test_array_sized_from_the_instrumenter(self):
        """instrument.py prints BRANCH_COUNTERS = 2 x ids; compiled with that value (as
        c2obra.sh does) every condition is evaluated. 50 decisions, all true."""
        n = 50
        code = ('#include <stdio.h>\nint main(void) {\n  volatile int a = 1; int s = 0;\n'
                + ''.join('  if (a > 0) s++;\n' for _ in range(n))
                + '  printf("%d\\n", s);\n  return 0;\n}\n')
        with tempfile.TemporaryDirectory() as d:
            orig, inst, out = instrument(d, 'r3.c', code)
            self.assertIn(f'BRANCH_COUNTERS={2 * n}', out)
            got = build_and_run(d, inst, RUNTIME + [f'-DMAX_BRANCHES={2 * n}'])
            self.assertEqual(got, build_and_run(d, orig))
            self.assertEqual(got, (0, f'{n}\n'))


class W3bUnbracedSwitchBody(unittest.TestCase):
    def test_unbraced_switch_body_stops_instrumentation(self):
        """switch (x) case 1: ... (no braces): Tree-sitter has no switch node at Clang's
        position, so instrumentation stops with a pairing error (no instrumented output)."""
        code = 'int f(int x) { switch (x) case 1: return 10; return 20; }\n'
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as cm:
                instrument(d, 'w3.c', code)
            self.assertEqual(cm.exception.code, 1)
            self.assertFalse(os.path.exists(os.path.join(d, 'w3_inst.c')))


R1_C = r'''#include <stdio.h>
int deep(int n) {
    volatile char buf[256];
    buf[0] = (char)n;
    if (n == -1) return 0;
    return deep(n + 1) + buf[0];
}
int main(void) {
    int a = 1;
    if (a > 0) printf("start\n");
    fflush(stdout);
    return deep(0);
}
'''


def no_core_dump():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class R1StackOverflow(unittest.TestCase):
    @unittest.expectedFailure
    def test_stack_overflow_keeps_coverage(self):
        """Unbounded recursion: SIGSEGV on stack overflow. The handler in cov_runtime.c runs on
        the same (full) stack (no sigaltstack), so the process dies and coverage.json is not
        written."""
        with tempfile.TemporaryDirectory() as d:
            _, inst, _ = instrument(d, 'r1.c', R1_C)
            exe = os.path.join(d, 'r1')
            subprocess.run(['gcc', '-w', '-o', exe, inst, *RUNTIME, '-I', SRC], check=True)
            cov = os.path.join(d, 'coverage.json')
            r = subprocess.run([exe], cwd=d, env=dict(os.environ, COVERAGE_OUTPUT=cov),
                               capture_output=True, text=True, timeout=30, preexec_fn=no_core_dump)
            self.assertEqual(r.returncode, -11)                 # SIGSEGV
            self.assertTrue(os.path.exists(cov), 'no coverage.json after stack overflow')


if __name__ == '__main__':
    unittest.main()
