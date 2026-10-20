"""Tests for the Clang/Tree-sitter pairing in instrument.py (Phase 2).

Clang decides which decisions exist; each must pair with a Tree-sitter node at the same
(kind, line, column), otherwise instrumentation stops.

Run from the repo root:  python3 -m unittest discover -s tests -p "test_*.py" -v
"""
import contextlib, io, json, os, re, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)
import instrument as I
from test_id_sync import cover_ids

CORPUS = os.path.join(HERE, 'corpusC')


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


class PairDecisions(unittest.TestCase):
    def test_decision_without_tree_sitter_node_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'int f(int x) { if (x) return 1; return 0; }\n')
            tree, src = I.parse_c_file(p)
            fake = [{'kind': 'while', 'line': 1, 'col': 16, 'n_cases': None}]
            with self.assertRaisesRegex(I.PairingError, r't\.c:1:16: while'):
                I.pair_decisions(fake, I.find_branches(tree), src, p)

    def test_tree_sitter_nodes_without_decision_are_returned_unpaired(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_tmp(d, 'int f(int x) { for (;;) { if (x) return 1; } }\n')
            tree, src = I.parse_c_file(p)
            ifs = [{'kind': 'if', 'line': 1, 'col': 27, 'n_cases': None}]
            paired, unpaired = I.pair_decisions(ifs, I.find_branches(tree), src, p)
        self.assertEqual([b['type'] for b in paired], ['if_statement'])
        self.assertEqual([b['type'] for b in unpaired], ['for_statement'])


class InstrumentFile(unittest.TestCase):
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

    def test_switch_labels_from_macro_stop_instrumentation(self):
        code, out, _, _ = run(os.path.join(CORPUS, 'c07_xmacro_switch.c'), flags=[])
        self.assertEqual(code, 1)
        self.assertIn('c07_xmacro_switch.c:9:3: switch', out)

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
            if not f.endswith('.c') or f.startswith('c07'):
                continue
            with self.subTest(file=f):
                code, _, inst, ids = run(os.path.join(CORPUS, f), flags=[])
                self.assertEqual(code, 0)
                self.assertEqual(cover_ids(inst), ids)


if __name__ == '__main__':
    unittest.main()
