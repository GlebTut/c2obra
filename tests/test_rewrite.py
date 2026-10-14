"""Instrumented code must compile and behave exactly like the original.

Each case is a small C function shaped after code where the rewriter produced broken output
(examples from Lua 5.4.6 / zlib 1.3.1, Phase 2 step 4). The original and the instrumented
program are compiled with gcc, run, and their output compared.

Run from the repo root:  python3 -m unittest discover -s tests -p "test_*.py" -v
"""
import contextlib, io, json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)
import instrument as I
from test_id_sync import cover_ids

MAIN = r'''
#include <stdio.h>
int main(void) {
    for (int v = -3; v <= 9; v++) printf("%d ", f(v));
    printf("\n");
    return 0;
}
'''

MAIN_DECISIONS = 1                                 # the for loop in MAIN


def build_and_run(d, c_file, extra=()):
    exe = c_file[:-2]
    r = subprocess.run(['gcc', '-w', '-o', exe, c_file, *extra, '-I', SRC], capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(f"gcc failed on {os.path.basename(c_file)}:\n{r.stderr}")
    env = dict(os.environ, COVERAGE_OUTPUT=os.path.join(d, 'coverage.json'))
    return subprocess.run([exe], capture_output=True, text=True, check=True, cwd=d, env=env).stdout


def counters(d):
    """{branch id: (true count, false count)} from the instrumented run's coverage.json."""
    with open(os.path.join(d, 'coverage.json')) as f:
        return {b['id']: (b['true'], b['false']) for b in json.load(f)['branches']}


class RewriteKeepsBehaviour(unittest.TestCase):
    def check(self, func, n_decisions):
        """Instrument func + MAIN; assert the instrumented program prints what the original prints,
        that func's n_decisions (+1 for MAIN's for loop) got a cover() ID, and that IDs match
        the branch map. Returns the coverage counters of the instrumented run."""
        with tempfile.TemporaryDirectory() as d:
            orig = os.path.join(d, 'orig.c')
            with open(orig, 'w') as f:
                f.write(func + MAIN)
            inst = os.path.join(d, 'inst_inst.c')
            with contextlib.redirect_stdout(io.StringIO()):
                I.instrument_file(orig, inst, flags=[])
            with open(inst) as f:
                code = f.read()
            with open(inst.replace('.c', '_branch_map.json')) as f:
                ids = [b['id'] for b in json.load(f)['branches']]
            self.assertEqual(len(ids), n_decisions + MAIN_DECISIONS)
            self.assertEqual(cover_ids(code), ids)
            expected = build_and_run(d, orig)
            got = build_and_run(d, inst, [os.path.join(SRC, 'cov_runtime.c')])
            self.assertEqual(got, expected)
            return counters(d)

    # R2: a top-level comma in a condition split the cover() macro arguments.
    def test_comma_in_while_condition(self):        # llex.c:365, ltablib.c:313
        self.check('static int g(int *i) { return ++*i; }\n'
                   'int f(int n) { int i = 0, s = 0; while ((void)g(&i), i < n) s += i; return s; }\n', 1)

    def test_comma_in_if_condition(self):
        self.check('int f(int n) { int t; if (t = n * 2, t > 4) return t; return -t; }\n', 1)

    def test_comma_in_for_condition(self):
        self.check('int f(int n) { int i, s = 0; for (i = 0; s += i, i < n; i++) ; return s; }\n', 1)

    # Same class: switch chain compared the expression without parentheses (x & 3 == 1).
    # The chain only records coverage, so the bug gave wrong counts, not wrong behaviour.
    def test_switch_expression_with_lower_precedence_operator(self):
        cov = self.check('int f(int n) { switch (n & 3) { case 1: return 10; case 2: return 20; default: return 0; } }\n', 3)
        # f runs for n = -3..9: n & 3 == 1 for 4 of them, == 2 for 3, default for the other 6.
        self.assertEqual([cov[1][0], cov[2][0], cov[3][0]], [4, 3, 6])

    # R1: a decision inside another decision's condition gave overlapping edits, and the old
    # SourceRewriter copied the overlapped text twice. Each test also checks that the inner
    # decision is counted (inside-out: no decision lost).
    def test_ternary_inside_if_condition(self):      # lua.c:480
        cov = self.check('static int g(int x) { return x; }\n'
                         'int f(int n) { if (g(n > 0 ? 1 : 2) == 1) return 7; return 8; }\n', 2)
        self.assertEqual(cov[2], (9, 4))             # n > 0 for 9 of the 13 inputs -3..9

    def test_ternary_in_call_inside_negated_if(self):   # lvm.c:184
        self.check('static int h(int a, int b) { return a + b > 4; }\n'
                   'int f(int n) { if (!h(n, (n < 0 ? 3 : 4))) return 1; return 2; }\n', 2)

    def test_ternary_inside_while_condition(self):   # liolib.c:472
        self.check('int f(int n) { int k = 0; while ((n & 1 ? k < 3 : k < 5) && k < 10) k++; return k; }\n', 2)

    def test_ternary_in_subtraction_inside_if(self):  # infback.c:565
        self.check('int f(int n) { int w = 4; if (n > w - (n < w ? 1 : 0)) return 1; return 0; }\n', 2)

    def test_ternary_in_ternary_condition(self):
        self.check('int f(int n) { return (n > 0 ? n : -n) > 3 ? 1 : 0; }\n', 2)

    def test_ternary_inside_for_condition(self):
        self.check('int f(int n) { int i, s = 0; for (i = 0; i < (n > 0 ? n : 0); i++) s += i; return s; }\n', 2)


class SwitchEvaluatedOnce(unittest.TestCase):
    """The cover chain inserted before switch (e) must not evaluate e again: with a side effect
    (switch (next()), switch ((*i)++)) the instrumented program would behave differently."""

    def test_switch_expression_with_side_effect(self):
        path = os.path.join(HERE, 'corpusC', 'c15_switch_side_effect.c')
        with tempfile.TemporaryDirectory() as d:
            inst = os.path.join(d, 'c15_inst.c')
            with contextlib.redirect_stdout(io.StringIO()):
                I.instrument_file(path, inst, flags=[])
            orig = os.path.join(d, 'c15.c')
            with open(path) as src, open(orig, 'w') as dst:
                dst.write(src.read())
            expected = build_and_run(d, orig)
            self.assertEqual(expected, 'calls=1 r=10 picks=100,101,199 i=3\n')   # the file itself
            got = build_and_run(d, inst, [os.path.join(SRC, 'cov_runtime.c')])
            self.assertEqual(got, expected)


class SourceRewriterUnit(unittest.TestCase):
    def test_nested_wraps_apply_inside_out(self):
        src = b'if (g(a ? 1 : 2)) x;'
        rw = I.SourceRewriter(src)
        outer = src.index(b'(g(');                  # (g(a ? 1 : 2))
        rw.wrap(outer, src.index(b' x;'), '(cover(', ', 1))')
        rw.wrap(src.index(b'a'), src.index(b'a') + 1, 'cover((', '), 2)')
        rw.insert(0, '/*chain*/')
        self.assertEqual(rw.apply(), '/*chain*/if (cover((g(cover((a), 2) ? 1 : 2)), 1)) x;')

    def test_partial_overlap_is_an_error(self):
        rw = I.SourceRewriter(b'0123456789')
        rw.wrap(1, 5, '[', ']')
        rw.wrap(3, 8, '<', '>')
        with self.assertRaises(ValueError):
            rw.apply()


if __name__ == '__main__':
    unittest.main()
