"""Tests for build_branches() in instrument.py.

Clang decides which decisions exist and gives the text range of each; a decision without a
range to wrap stops instrumentation (PairingError).

Run from the repo root:  python3 -m unittest discover -s unittests -p "test_*.py" -v
"""
import contextlib, io, json, os, re, subprocess, sys, tempfile, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, '..', 'tests')   # test inputs (unittests/ holds the code)
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)
import clang_scan
import instrument as I
from test_id_sync import cover_ids
from test_c2obra_sh import can_build_m32

CORPUS = os.path.join(TESTS, 'corpusC')
SRC = os.path.join(HERE, '..', 'src')


def run(path, flags=None):
    """instrument_file() into a temp dir: (exit code, stdout, instrumented code, map ids)."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'out_inst.c')
        buf = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(buf):
            try:
                I.instrument_file(path, out, flags=flags)
            except SystemExit as e:
                code = e.code
        if code:
            return code, buf.getvalue(), None, None
        with open(out) as f:
            inst = f.read()
        with open(out.replace('.c', '_branch_map.json')) as f:
            ids = [b['id'] for b in json.load(f)['branches']]
        return code, buf.getvalue(), inst, ids


def write_tmp(d, text):
    p = os.path.join(d, 't.c')
    with open(p, 'w') as f:
        f.write(text)
    return p


class BuildBranches(unittest.TestCase):
    def test_decision_without_plain_text_span_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'int f(int x) { if (x) return 1; return 0; }\n')
            src = open(p, 'rb').read()
            fake = [{'kind': 'while', 'line': 1, 'col': 16, 'offset': 15, 'cond_span': None,
                     'has_condition': True, 'for_semis': None}]
            with self.assertRaisesRegex(I.PairingError, r't\.c:1:16: while'):
                I.build_branches(fake, src, p)

    def test_branches_come_back_in_source_order_with_clang_spans(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'int f(int x) { for (;;) { if (x) return 1; } }\n')
            src = open(p, 'rb').read()
            decisions, _ = clang_scan.decisions(p, [])
            branches = I.build_branches(list(reversed(decisions)), src, p)
        self.assertEqual([b['type'] for b in branches], ['for_statement', 'if_statement'])
        self.assertIsNone(branches[0]['cond_span'])       # for(;;): no condition, a slot instead
        self.assertIsNotNone(branches[0]['slot'])
        self.assertEqual(src[slice(*branches[1]['cond_span'])], b'x')


class MacroCaseLabels(unittest.TestCase):
    def test_case_labels_written_as_macros_are_instrumented(self):
        """`case NAME:`, `case F(2):` and `case LO ... 9:` keep the text written in the file."""
        code = ('#define A 1\n#define F(x) ((x)+1)\n#define R 7\n'
                'int f(int c) { switch (c) { case A: return 1; case F(2): return 2;'
                ' case R ... 9: return 3; default: return 0; } }\n')
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, code)
            src = open(p, 'rb').read()
            decisions, _ = clang_scan.decisions(p, [])
            out = I.instrument_code(src, I.build_branches(decisions, src, p))
        self.assertIn('cover((__c2obra_sw_1) == (A), 1)', out)
        self.assertIn('cover((__c2obra_sw_1) == (F(2)), 2)', out)
        self.assertIn('(__c2obra_sw_1) >= (R) && (__c2obra_sw_1) <= (9)', out)


class InstrumentFile(unittest.TestCase):
    def test_timing_file_only_when_asked(self):
        path = os.path.join(CORPUS, 'c03_ifdef_split_braces.c')
        with tempfile.TemporaryDirectory() as d:
            t = os.path.join(d, 'timing.json')
            with unittest.mock.patch.dict(os.environ, {'C2OBRA_TIMING_FILE': t}):
                self.assertEqual(run(path, flags=[])[0], 0)
            with open(t) as f:
                timing = json.load(f)
            self.assertEqual(sorted(timing), ['instrument', 'parse'])
            self.assertTrue(all(v >= 0 for v in timing.values()))
            os.remove(t)
            with unittest.mock.patch.dict(os.environ):
                os.environ.pop('C2OBRA_TIMING_FILE', None)
                run(path, flags=[])
            self.assertFalse(os.path.exists(t))

    def test_flags_choose_the_ifdef_arm(self):
        path = os.path.join(CORPUS, 'c03_ifdef_split_braces.c')
        _, _, inst, _ = run(path, flags=[])
        self.assertIn('if (cover((a >= 0), 1))', inst)
        self.assertNotIn('cover(a > 0', inst)
        _, _, inst, _ = run(path, flags=['-DFAST'])
        self.assertIn('if (cover((a > 0), 1))', inst)
        self.assertNotIn('cover(a >= 0', inst)

    def test_define_adds_a_branch(self):
        path = os.path.join(CORPUS, 'c05_flag_dependent.c')
        self.assertEqual(len(run(path, flags=[])[3]), 1)
        self.assertEqual(len(run(path, flags=['-DDEBUG'])[3]), 2)

    def test_macro_decisions_are_skipped_with_a_count(self):
        code, out, inst, ids = run(os.path.join(CORPUS, 'c02_macro_condition_and_keyword.c'), flags=[])
        self.assertEqual(code, 0)
        self.assertIn('Skipped 1 Clang decision(s): macro', out)
        self.assertEqual(ids, [1])
        self.assertIn('if (cover((IS_NEG(a)), 1))', inst)

    def test_for_without_condition_gets_cover_in_its_empty_slot(self):
        # for(;;) counts like while(1). Regression guard: the old get_for_condition_node fallback
        # took the initializer (i = 0) as the condition; it must stay unwrapped.
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'int f(int n) { int i; for (i = 0; ; i++) if (i > n) break; return i; }\n')
            code, _, inst, ids = run(p, flags=[])
        self.assertEqual(code, 0)
        self.assertIn('for (i = 0; cover((1), 1); i++)', inst)
        self.assertEqual(ids, [1, 2])

    def test_switch_labels_from_macro_are_skipped_with_a_count(self):
        """X-macro case labels: no text to wrap. The switch is left out (like a macro
        decision) and counted in the message; the file is still written."""
        code, out, inst, ids = run(os.path.join(CORPUS, 'c07_xmacro_switch.c'), flags=[])
        self.assertEqual(code, 0, out)
        self.assertIn('Skipped 1 Clang decision(s): switch with case labels written by a macro', out)
        self.assertEqual(ids, [])

    def test_macro_call_as_condition_stops_instrumentation(self):
        code, out, _, _ = run(os.path.join(TESTS, 'pairing_error', 'if_macro_call.c'), flags=[])
        self.assertEqual(code, 1)
        self.assertIn('if_macro_call.c:7:3: if', out)

    def test_compiler_error_stops_and_shows_flags(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'int f(int x) { if (x < LARGE_INT) return 1; return 0; }\n')
            code, out, _, _ = run(p, flags=['-DOTHER=1'])
            self.assertEqual(code, 1)
            self.assertIn("'LARGE_INT'", out)
            self.assertIn('-DOTHER=1', out)
            self.assertEqual(run(p)[0], 0)        # default SV-COMP flags define it

    def test_ids_match_map_on_every_corpus_file_that_instruments(self):
        for f in sorted(os.listdir(CORPUS)):
            if not f.endswith('.c'):
                continue
            with self.subTest(file=f):
                code, _, inst, ids = run(os.path.join(CORPUS, f), flags=[])
                self.assertEqual(code, 0)
                self.assertEqual(cover_ids(inst), ids)


class OutsideFunctions(unittest.TestCase):
    """Run 2026-10-20: 19 busybox tasks failed to compile with "enumerator value for '_ISupper'
    is not an integer constant": glibc <ctype.h>'s enum values were wrapped in cover()."""
    SRC_TEXT = ('enum { A = ((0) < 8 ? 1 : 2) };\n'
                'int main(void) { int x = A; return x > 0 ? 0 : 1; }\n')

    def test_enum_ternary_is_left_alone_and_compiles(self):
        models = ['-m64'] + (['-m32'] if can_build_m32() else [])
        for flag in models:
            with self.subTest(model=flag), tempfile.TemporaryDirectory() as d:
                p = write_tmp(d, self.SRC_TEXT)
                inst = os.path.join(d, 't_inst.c')
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    I.instrument_file(p, inst, flags=[flag])
                self.assertIn('Skipped 1 Clang decision(s): outside_function', buf.getvalue())
                with open(inst) as f:
                    code = f.read()
                self.assertIn('enum { A = ((0) < 8 ? 1 : 2) };', code)
                self.assertIn('cover((x > 0), 1)', code)                # the ?: in main is still wrapped
                self.assertEqual(cover_ids(code), [1])
                r = subprocess.run(['gcc', '-w', flag, inst, os.path.join(SRC, 'cov_runtime.c'),
                                    os.path.join(SRC, 'verifier_stubs.c'), '-I', SRC, '-o', os.path.join(d, 't')],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
