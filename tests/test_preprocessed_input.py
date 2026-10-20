"""Preprocessed (.i) input: instrument.py accepts it and counts the same edges as the .c.

Each tests/definition program is run through `gcc -E` (gcc line markers kept, as in many
Test-Comp .i files) and through `gcc -E -P` (no markers). The .i is instrumented, built and run
like test_definition.py does, and must give the edges in expected.csv. Branch-map lines are the
physical lines of the .i file (Clang's expansion location, not the line the markers name).

Not covered: .i files made from glibc >= 2.34 headers. Their __attribute__((__malloc__(f)))
is GCC-only, and the Clang scan stops with an error (seen with a local gcc 13 / glibc 2.39 .i).

Run from the repo root:  python3 -m unittest tests.test_preprocessed_input -v
"""
import contextlib, io, json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_definition as TD          # build_and_run, expected_rows, SRC, DEFS
import instrument as I
import edges as E


def preprocess(d, name, plain):
    """gcc -E [-P] tests/definition/<name> -> d/<stem>.i"""
    out = os.path.join(d, name[:-2] + '.i')
    cmd = ['gcc', '-E', *(['-P'] if plain else []), os.path.join(TD.DEFS, name), '-o', out]
    subprocess.run(cmd, check=True)
    return out


def instrument_i(d, i_file):
    inst = os.path.join(d, os.path.basename(i_file)[:-2] + '_inst.c')
    with contextlib.redirect_stdout(io.StringIO()):
        I.instrument_file(i_file, inst, flags=[])
    with open(inst[:-2] + '_branch_map.json') as f:
        return inst, json.load(f)


class PreprocessedInput(unittest.TestCase):
    def test_edges_match_expected_csv(self):
        for plain in (False, True):
            for row in TD.expected_rows():
                if row['file'] == 'd15_macros.c':       # macros: see the two d15 tests below
                    continue
                with self.subTest(file=row['file'], markers=not plain), tempfile.TemporaryDirectory() as d:
                    i_file = preprocess(d, row['file'], plain)
                    inst, branch_map = instrument_i(d, i_file)
                    TD.build_and_run(d, inst, [os.path.join(TD.SRC, 'cov_runtime.c'),
                                               os.path.join(TD.SRC, 'verifier_stubs.c')])
                    with open(os.path.join(d, 'coverage.json')) as f:
                        coverage = {b['id']: b for b in json.load(f)['branches']}
                    self.assertEqual(E.edge_coverage(branch_map, coverage),
                                     (int(row['covered_edges']), int(row['total_edges'])))

    def test_d15_macro_decisions_are_counted_in_i(self):
        """In the .c, MAX's ?: and assert's ?: and if are macro-only and skipped (1 decision,
        2 edges). After gcc -E they are plain text, so the .i has 4 decisions, 8 edges:
        MAX ?: (x > y false: 1 edge), assert sizeof ?: (never evaluated: 0), assert if
        (m >= 0 true: 1), if (m > 5) (m = 4, false: 1) -> 3/8."""
        with tempfile.TemporaryDirectory() as d:
            i_file = preprocess(d, 'd15_macros.c', plain=True)
            inst, branch_map = instrument_i(d, i_file)
            self.assertEqual(sorted(b['type'] for b in branch_map['branches']),
                             ['if_statement', 'if_statement', 'ternary_expression', 'ternary_expression'])
            TD.build_and_run(d, inst, [os.path.join(TD.SRC, 'cov_runtime.c'),
                                       os.path.join(TD.SRC, 'verifier_stubs.c')])
            with open(os.path.join(d, 'coverage.json')) as f:
                coverage = {b['id']: b for b in json.load(f)['branches']}
            self.assertEqual(E.edge_coverage(branch_map, coverage), (3, 8))

    def test_d15_markers_inside_expression_stop_pairing(self):
        """gcc -E puts line markers inside assert()'s expansion; Tree-sitter has no node there,
        so pairing stops (a hard error, as designed). The batch driver cleans markers first."""
        with tempfile.TemporaryDirectory() as d:
            i_file = preprocess(d, 'd15_macros.c', plain=False)
            with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()) as out:
                I.instrument_file(i_file, os.path.join(d, 'd15_macros_inst.c'), flags=[])
            self.assertIn('could not be paired', out.getvalue())

    def test_lines_are_physical_lines_of_the_i_file(self):
        keyword = {'if_statement': 'if', 'for_statement': 'for', 'while_statement': 'while'}
        with tempfile.TemporaryDirectory() as d:
            i_file = preprocess(d, 'd07_for_infinite.c', plain=False)
            with open(i_file) as f:
                lines = f.read().split('\n')
            self.assertTrue(lines[0].startswith('# '), 'expected gcc line markers in the .i')
            _, branch_map = instrument_i(d, i_file)
            for b in branch_map['branches']:
                self.assertIn(keyword[b['type']], lines[b['line'] - 1])

    def test_other_extensions_still_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            h = os.path.join(d, 'x.h')
            open(h, 'w').close()
            with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
                I.instrument_file(h, os.path.join(d, 'x_inst.c'), flags=[])


if __name__ == '__main__':
    unittest.main()
