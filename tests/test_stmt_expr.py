"""GNU statement expressions '({ ... })' in if/while/do/for headers.

tree-sitter-c 0.21.3 has no rule for them, so the decision's node is missing (if, while) or
its condition span is wrong (for: it wrapped the 't' of the init's ({ })). For such headers
pair_decisions() wraps Clang's condition span instead (clang_branch()). Every other header
is paired as before.

tests/stmtexpr/stmtexpr_{b,c,d}.c are copies of ~/benchmarks/runs/2026-10-25_stmtexpr/src/.

Run from the repo root:  python3 -m unittest discover -s tests -p "test_*.py" -v
"""
import contextlib, io, json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
CASES = os.path.join(HERE, 'stmtexpr')
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)
import instrument as I
import clang_scan as C
from test_id_sync import cover_ids


def instrument(d, path):
    """instrument_file() into d: (exit code, stdout, instrumented code or None, map or None)."""
    out = os.path.join(d, os.path.basename(path)[:-2] + '_inst.c')
    buf, code = io.StringIO(), 0
    with contextlib.redirect_stdout(buf):
        try:
            I.instrument_file(path, out, flags=[])
        except SystemExit as e:
            code = e.code
    if code:
        return code, buf.getvalue(), None, None
    with open(out) as f:
        inst = f.read()
    with open(out[:-2] + '_branch_map.json') as f:
        return code, buf.getvalue(), inst, json.load(f)


def compile_and_run(d, inst_code):
    """Compile and link with the runtime, run with no input. (exit code, coverage by id)."""
    c_file, exe = os.path.join(d, 'prog_inst.c'), os.path.join(d, 'prog')
    with open(c_file, 'w') as f:
        f.write(inst_code)
    r = subprocess.run(['gcc', '-w', '-o', exe, c_file, os.path.join(SRC, 'cov_runtime.c'),
                        os.path.join(SRC, 'verifier_stubs.c'), '-I', SRC], capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(f"gcc failed:\n{r.stderr}")
    cov = os.path.join(d, 'coverage.json')
    r = subprocess.run([exe], capture_output=True, text=True, cwd=d, timeout=30,
                       stdin=subprocess.DEVNULL, env=dict(os.environ, COVERAGE_OUTPUT=cov))
    with open(cov) as f:
        return r.returncode, {b['id']: b for b in json.load(f)['branches']}


def write(d, text, name='t.c'):
    p = os.path.join(d, name)
    with open(p, 'w') as f:
        f.write(text)
    return p


def body(inst):
    """The instrumented code without the preamble lines added by instrument_code()."""
    return inst.split('extern void __VERIFIER_assume(int);\n\n', 1)[1]


class BenchmarkCases(unittest.TestCase):
    def test_for_header_wraps_the_real_condition(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, inst, bmap = instrument(d, os.path.join(CASES, 'stmtexpr_c.c'))
            self.assertEqual(code, 0, out)
            self.assertIn('for (i = ({ int t = 0; t; });  cover((i < ({ int t = 2; t; })), 1) ; i++)', inst)
            self.assertEqual(cover_ids(inst), [b['id'] for b in bmap['branches']])
            rc, cov = compile_and_run(d, inst)
        # i = 0, 1 enter the loop, i = 2 leaves it; the program returns a + s = 0 + 1
        self.assertEqual((cov[1]['true'], cov[1]['false']), (2, 1))
        self.assertEqual(rc, 1)

    def test_if_and_while_instrument_and_compile(self):
        for name, wrap in (('stmtexpr_b.c', 'if (cover((({ int t = x; t > 3; })), 1))'),
                           ('stmtexpr_d.c', 'while (cover((({ int t = s; t > 0; })), 1))')):
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                code, out, inst, bmap = instrument(d, os.path.join(CASES, name))
                self.assertEqual(code, 0, out)
                self.assertIn(wrap, inst)
                self.assertEqual(len(bmap['edges']), 2)
                compile_and_run(d, inst)

    def test_if_branch_map_from_clang(self):
        # no Tree-sitter if node: line and else labels come from Clang
        with tempfile.TemporaryDirectory() as d:
            _, _, _, bmap = instrument(d, os.path.join(CASES, 'stmtexpr_b.c'))
            p = write(d, 'int f(int x) {\n  if (({ x > 1; }))\n    return 1;\n  else\n    return 2;\n}\n')
            _, _, _, bmap2 = instrument(d, p)
        self.assertEqual(bmap['branches'][0]['line'], 6)
        self.assertEqual(bmap['branches'][0]['false_label'], 'no else (false)')
        self.assertEqual(bmap2['branches'][0]['false_label'], 'else @ line 4')


class ForHeaders(unittest.TestCase):
    def test_plain_for_loops_unchanged(self):
        # no statement expression: Tree-sitter wraps as before
        with tempfile.TemporaryDirectory() as d:
            p = write(d, 'int f(int c) {\n  int i, s = 0;\n  for (; c; i++) s++;\n'
                         '  for (i = 0;; i++) break;\n  return s;\n}\n')
            code, out, inst, _ = instrument(d, p)
        self.assertEqual(code, 0, out)
        self.assertIn('for (;  cover((c), 1) ; i++) s++;', inst)
        self.assertIn('for (i = 0;cover((1), 2); i++) break;', inst)

    def test_for_without_init_takes_the_condition(self):
        # libclang gives children [cond, inc, body]: the ';' offsets pick the condition
        with tempfile.TemporaryDirectory() as d:
            p = write(d, 'int f(int i) {\n  int s = 0;\n  for (; i < ({ int t = 2; t; }); i++) s++;\n  return s;\n}\n')
            code, out, inst, _ = instrument(d, p)
        self.assertEqual(code, 0, out)
        self.assertIn('for (;  cover((i < ({ int t = 2; t; })), 1) ; i++)', inst)

    def test_for_without_condition_fills_the_slot(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, 'int f(void) {\n  int i;\n  for (i = ({ int t = 0; t; });; i++) break;\n  return i;\n}\n')
            code, out, inst, _ = instrument(d, p)
        self.assertEqual(code, 0, out)
        self.assertIn('for (i = ({ int t = 0; t; });cover((1), 1); i++)', inst)

    def test_scan_exports_semicolons_and_span(self):
        with tempfile.TemporaryDirectory() as d:
            text = 'int f(int i) {\n  for (; i < ({ int t = 2; t; }); i++) ;\n  return i;\n}\n'
            p = write(d, text)
            [dec] = C.scan(p)
        self.assertTrue(dec['header_stmt_expr'])
        s1, s2 = dec['for_semis']
        self.assertEqual((text[s1], text[s2]), (';', ';'))
        self.assertEqual(text[slice(*dec['cond_span'])], 'i < ({ int t = 2; t; })')
        self.assertEqual(dec['cond_lc'], ((2, 10), (2, 33)))


class OtherShapes(unittest.TestCase):
    def test_multi_line_condition(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, 'int main(void) {\n  int s = 2;\n  while (s >\n'
                         '         ({ int u = 0;\n            u; }))\n    s--;\n  return s;\n}\n')
            code, out, inst, _ = instrument(d, p)
            self.assertEqual(code, 0, out)
            self.assertIn('while (cover((s >\n         ({ int u = 0;\n            u; })), 1))', inst)
            rc, cov = compile_and_run(d, inst)
        self.assertEqual((cov[1]['true'], cov[1]['false']), (2, 1))

    def test_ternary_inside_header_statement_expression(self):
        # the ?: has its own Tree-sitter node; its wrap nests inside the for condition's wrap
        with tempfile.TemporaryDirectory() as d:
            p = write(d, 'int main(void) {\n  int i, s = 0, x = 1;\n'
                         '  for (i = 0; i < ({ int t = x ? 2 : 3; t; }); i++) s++;\n  return s;\n}\n')
            code, out, inst, bmap = instrument(d, p)
            self.assertEqual(code, 0, out)
            self.assertIn(' cover((i < ({ int t = cover((x), 2) ? 2 : 3; t; })), 1) ', inst)
            self.assertEqual(cover_ids(inst), [b['id'] for b in bmap['branches']])
            rc, cov = compile_and_run(d, inst)
        self.assertEqual(rc, 2)
        self.assertEqual((cov[1]['true'], cov[1]['false']), (2, 1))
        self.assertEqual((cov[2]['true'], cov[2]['false']), (3, 0))

    def test_if_inside_while_header_statement_expression(self):
        # Tree-sitter's error recovery keeps this inner if node: its wrap nests in the while's
        with tempfile.TemporaryDirectory() as d:
            p = write(d, 'int main(void) {\n  int i = 2;\n  while (({ int t = i; if (t) t++; t > 1; })) i--;\n  return i;\n}\n')
            code, out, inst, _ = instrument(d, p)
            self.assertEqual(code, 0, out)
            self.assertIn('while (cover((({ int t = i; if (cover((t), 2)) t++; t > 1; })), 1)) i--;', inst)
            rc, cov = compile_and_run(d, inst)
        self.assertEqual(rc, 0)
        self.assertEqual((cov[1]['true'], cov[1]['false']), (2, 1))
        self.assertEqual((cov[2]['true'], cov[2]['false']), (2, 1))

    def test_if_inside_for_header_statement_expression_still_stops(self):
        # here Tree-sitter has no node for the inner if, whose own header has no statement
        # expression, so it is paired as before: hard PairingError (decision 2026-10-25)
        with tempfile.TemporaryDirectory() as d:
            p = write(d, 'int f(int i) {\n  for (; i < ({ int t = 2; if (t) t++; t; }); i++) ;\n  return i;\n}\n')
            code, out, _, _ = instrument(d, p)
        self.assertEqual(code, 1)
        self.assertRegex(out, r't\.c:2:28: if: Clang sees a decision here, Tree-sitter has no if node')

    def test_partly_overlapping_wraps_are_a_pairing_error(self):
        src = b'int f(int a, int b) { return a + b; }\n'
        crossing = [{'type': 'if_statement', 'node': None, 'start_byte': s, 'start_point': (0, s),
                     'cond_span': (s, e), 'slot': None} for s, e in ((29, 33), (31, 35))]
        with self.assertRaisesRegex(I.PairingError, r'1:32: two cover\(\) wraps partly overlap'):
            I.instrument_code(src, crossing)


if __name__ == '__main__':
    unittest.main()
