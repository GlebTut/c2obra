"""Tests for src/clang_scan.py: which decisions Clang reports, and when the scan must stop.

The stress files in tests/corpusC carry hand-written expectations (written before any tool
was run, see the 5.3 study):
  // E: <kinds>          decisions starting on this line
  // E[DEFINE]: <kinds>  only when compiled with -DDEFINE
  // E@N: <kinds>        decisions starting on line N
They count every decision in the compiled program, including macro-produced ones, so they
are compared with the raw scan; which of them the filter skips is tested separately.

Run from the repo root:  python3 -m unittest discover -s tests -p "test_*.py" -v
"""
import os, re, sys, tempfile, unittest
from collections import Counter
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import clang_scan as C

CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'corpusC')
KIND_WORDS = {'if', 'for', 'while', 'do', 'switch', '?:'}
E_RE = re.compile(r'//\s*E(?:\[(\w+)\])?(?:@(\d+))?:\s*(.*)')


def expectations(path):
    """{define or None: Counter((kind, line))} from the // E comments."""
    out = {}
    with open(path) as f:
        lines = f.readlines()
    for n, text in enumerate(lines, 1):
        m = E_RE.search(text)
        if not m:
            continue
        define, at, rest = m.group(1), m.group(2), m.group(3).split()
        line = int(at) if at else n
        kinds = []
        for w in rest:                       # stop at the first word that is not a kind
            if w not in KIND_WORDS:
                break
            kinds.append(w)
        out.setdefault(define, Counter()).update((k, line) for k in kinds)
    return out


def got(path, flags=()):
    """Decisions in the compiled program, as listed by the E: comments. Those comments do not
    list for(;;) (has_condition False), so it is left out here; the filter does count it."""
    return Counter((d['kind'], d['line']) for d in C.scan(path, list(flags)) if d['has_condition'] is not False)


def write_tmp(d, text):
    p = os.path.join(d, 't.c')
    with open(p, 'w') as f:
        f.write(text)
    return p


class CorpusCExpectations(unittest.TestCase):
    def test_every_file_matches_expectations(self):
        files = sorted(f for f in os.listdir(CORPUS) if f.endswith('.c'))
        self.assertEqual(len(files), 15)
        for f in files:
            path = os.path.join(CORPUS, f)
            exp = expectations(path)
            with self.subTest(file=f):
                self.assertEqual(got(path), exp.get(None, Counter()))
            for define, cons in exp.items():
                if define is None:
                    continue
                with self.subTest(file=f, define=define):
                    with_d = got(path, [f'-D{define}'])
                    self.assertEqual(with_d & cons, cons)          # appear with -D
                    self.assertFalse(got(path) & cons)             # absent without

    def test_ifdef_else_arm_is_dropped_when_define_given(self):
        # c03: with -DFAST the #else arm (line 6) is not compiled.
        path = os.path.join(CORPUS, 'c03_ifdef_split_braces.c')
        self.assertEqual(got(path, ['-DFAST']), Counter({('if', 4): 1}))

    def test_macro_flags(self):
        expected_macro = {
            'c01_macro_with_if.c':               {('do', 4), ('if', 4), ('do', 5), ('if', 5)},
            'c02_macro_condition_and_keyword.c': {('if', 7)},      # IS_NEG in the condition is not
            'c06_macro_loop_keyword.c':          {('for', 6), ('while', 7)},
            'c08_ternary_macros.c':              {('?:', 4), ('?:', 5)},
            'c10_include_header.c':              {('?:', 5)},
        }
        for f in sorted(os.listdir(CORPUS)):
            if not f.endswith('.c'):
                continue
            with self.subTest(file=f):
                macro = {(d['kind'], d['line']) for d in C.scan(os.path.join(CORPUS, f)) if d['from_macro']}
                self.assertEqual(macro, expected_macro.get(f, set()))

    def test_columns_are_one_based_expansion_columns(self):
        path = os.path.join(CORPUS, 'c11_kr_and_oddities.c')
        ifs = [(d['line'], d['col']) for d in C.scan(path) if d['kind'] == 'if']
        self.assertEqual(ifs, [(8, 5), (8, 16)])


class Filter(unittest.TestCase):
    def test_for_without_condition_is_kept(self):
        # for(;;) counts like while(1) (tests/definition/d07)
        kept, skipped = C.decisions(os.path.join(CORPUS, 'c11_kr_and_oddities.c'))
        self.assertEqual(skipped, Counter())
        self.assertEqual([(d['kind'], d['line']) for d in kept],
                         [('for', 6), ('for', 7), ('if', 8), ('if', 8)])

    def test_macro_decisions_are_skipped_and_counted(self):
        kept, skipped = C.decisions(os.path.join(CORPUS, 'c01_macro_with_if.c'))
        self.assertEqual(kept, [])
        self.assertEqual(skipped, Counter({'macro': 4}))

    def test_decisions_outside_functions_are_skipped_and_counted(self):
        # busybox <ctype.h>: _ISupper = ((0) < 8 ? ...) is an enum value, a constant expression
        # that cannot hold cover(). Also a global initialiser, a file-scope array size and a
        # parameter's array size; only the ?: in the function body is kept.
        src = ('enum { A = ((0) < 8 ? 1 : 2) };\n'
               'int g = 1 < 2 ? 3 : 4;\n'
               'int arr[(1 < 2) ? 3 : 4];\n'
               'int f(int n, int a[n ? 1 : 2]) { return n > 0 ? a[0] : A; }\n')
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, src)
            scanned = [(d['line'], d['in_function']) for d in C.scan(p)]
            kept, skipped = C.decisions(p)
        self.assertEqual(scanned, [(1, False), (2, False), (3, False), (4, False), (4, True)])
        self.assertEqual([(d['kind'], d['line']) for d in kept], [('?:', 4)])
        self.assertEqual(skipped, Counter({'outside_function': 4}))

    def test_switch_without_labels_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'int f(int x) { switch (x) { x++; } return x; }\n')
            kept, skipped = C.decisions(p)
        self.assertEqual(kept, [])
        self.assertEqual(skipped, Counter({'switch_no_case': 1}))

    def test_for_with_only_init_and_increment_has_no_condition(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'int f(int n) { int i; for (i = 0; ; i++) if (i > n) break; return i; }\n')
            kept, skipped = C.decisions(p)
        self.assertEqual([d['kind'] for d in kept], ['for', 'if'])
        self.assertEqual([d['has_condition'] for d in kept], [False, None])
        self.assertEqual(skipped, Counter())

    def test_switch_cases_of_nested_switch_are_not_counted(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'int f(int x, int y) { switch (x) { case 1: switch (y) { case 2: case 3: return 1; } '
                             'default: return 0; } }\n')
            cases = [d['n_cases'] for d in C.scan(p)]
        self.assertEqual(cases, [2, 2])


class FailLoudly(unittest.TestCase):
    def test_missing_clang_binary(self):
        with self.assertRaisesRegex(C.ClangScanError, 'print-resource-dir'):
            C.resource_dir(clang='no-such-clang-binary')

    def test_clang_binary_from_environment(self):
        C.resource_dir.cache_clear()
        self.addCleanup(C.resource_dir.cache_clear)
        with mock.patch.dict(os.environ, {'C2OBRA_CLANG': 'no-such-clang-18'}):
            with self.assertRaisesRegex(C.ClangScanError, "no-such-clang-18 -print-resource-dir"):
                C.resource_dir()

    def test_resource_dir_without_builtin_headers(self):
        C.resource_dir.cache_clear()             # resource_dir() is cached; force a real call
        self.addCleanup(C.resource_dir.cache_clear)
        with tempfile.TemporaryDirectory() as d:
            fake = mock.Mock(stdout=d + '\n')
            with mock.patch.object(C.subprocess, 'run', return_value=fake):
                with self.assertRaisesRegex(C.ClangScanError, 'stddef.h'):
                    C.resource_dir()

    def test_fatal_error_stops_with_file_diagnostic_and_flags(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, '#include "no_such_header.h"\nint f(int x) { if (x) return 1; return 0; }\n')
            with self.assertRaises(C.ClangScanError) as cm:
                C.scan(p, ['-DFOO=1'])
        msg = str(cm.exception)
        self.assertIn(p, msg)
        self.assertIn('no_such_header.h', msg)
        flags_line = next(l for l in msg.splitlines() if 'flags used:' in l)
        self.assertIn('-DFOO=1', flags_line)
        self.assertIn('-isystem', flags_line)

    def test_missing_define_is_an_error_until_given(self):
        # The SV-COMP LARGE_INT case: the identifier only exists if -D supplies it.
        src = 'int f(int x) { if (x < LARGE_INT) return 1; return 0; }\n'
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, src)
            with self.assertRaisesRegex(C.ClangScanError, 'LARGE_INT'):
                C.scan(p)
            self.assertEqual(len(C.scan(p, ['-DLARGE_INT=1000000'])), 1)

    def test_leniency_flags_accept_what_gcc_only_warns_about(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'f(x) { if (g(x)) return 1; return 0; }\n')   # implicit int + implicit decl
            self.assertEqual([d['kind'] for d in C.scan(p)], ['if'])

    def test_incompatible_function_pointer_is_accepted(self):
        # ntdrivers cdaudio/parport: a callback assigned from a function with another parameter type
        src = ('typedef int (*cb_t)(void *);\nstatic int h(int *p) { return *p; }\n'
               'int f(void) { cb_t c; c = h; if (c) return 1; return 0; }\n')
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, src)
            self.assertEqual([d['kind'] for d in C.scan(p)], ['if'])

    def test_user_can_override_leniency(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'int f(int x) { if (g(x)) return 1; return 0; }\n')
            with self.assertRaisesRegex(C.ClangScanError, 'implicit'):
                C.scan(p, ['-Werror=implicit-function-declaration'])


if __name__ == '__main__':
    unittest.main()
