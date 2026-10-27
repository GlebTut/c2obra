"""report.py --mode testcov: TestCov's goal definition from C²oBra's counters (docs/testcov_mode.md).

Each of tests/definition/d01-d15 is instrumented and run as in test_definition.py, and the
goals of src/testcov_goals.py are compared with what TestCov measured on the same program with
one empty test (tests/definition/testcov_results/results.csv). d15: TestCov fails on it
("else without a previous if"), so there is no number to match; the mode's result is recorded.

Run from the repo root:  python3 -m unittest tests.test_testcov_mode -v
"""
import csv, json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
DEFS = os.path.join(HERE, 'definition')
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)
import testcov_goals as G
from test_definition import instrument_and_run


def testcov_rows():
    with open(os.path.join(DEFS, 'testcov_results', 'results.csv')) as f:
        return {r['program'] + '.c': r for r in csv.DictReader(f)}


def mode_result(name):
    with tempfile.TemporaryDirectory() as d:
        branch_map, coverage, _, _ = instrument_and_run(d, name)
        return G.goals(branch_map, coverage, os.path.join(d, name))


class MatchesTestCov(unittest.TestCase):
    def test_all_definition_programs(self):
        rows = testcov_rows()
        self.assertEqual(len(rows), 15)
        for name, row in sorted(rows.items()):
            with self.subTest(program=name):
                r = mode_result(name)
                self.assertEqual(r['unmatched'], [])
                if row['status'] == 'ok':
                    self.assertEqual((r['covered'], r['total']),
                                     (int(row['goals_covered']), int(row['goals_total'])))
                else:                                   # d15: TestCov error, nothing to match
                    self.assertEqual(name, 'd15_macros.c')
                    self.assertEqual((r['covered'], r['total']), (1, 2))   # macro decisions not counted

    def test_goals_of_the_programs_that_differ_from_edges(self):
        reached = lambda name: [(g['kind'], g['reached']) for g in mode_result(name)['goals']]
        # else-if: no goal for the outer false side
        self.assertEqual(reached('d02_else_if.c'), [('if then', True), ('if then', True), ('if else', False)])
        # do-while: only the statement after the loop
        self.assertEqual(reached('d05_do_while.c'), [('after loop', True), ('after loop', True)])
        # while(1): the statement after the loop is reached through the break
        self.assertEqual(reached('d06_while1.c'),
                         [('loop body', True), ('after loop', True), ('if then', True), ('if else', True)])
        # no implicit default goal
        self.assertEqual(reached('d10_switch_no_default.c'), [('case label', True), ('case label', True)])
        # fall-through: case 2 is credited after case 1
        self.assertEqual(reached('d11_switch_fallthrough.c'),
                         [('case label', True), ('case label', True), ('case label', False)])
        # stacked labels: case 2 is reached from case 1
        self.assertEqual(reached('d12_switch_stacked.c'),
                         [('case label', True), ('case label', True), ('case label', True)])


class ReportCli(unittest.TestCase):
    def test_report_mode_testcov_writes_goal_csv(self):
        name = 'd11_switch_fallthrough.c'
        with tempfile.TemporaryDirectory() as d:
            branch_map, coverage, _, _ = instrument_and_run(d, name)
            bmap = os.path.join(d, name[:-2] + '_inst_branch_map.json')
            cov = os.path.join(d, 'cov.json')
            with open(cov, 'w') as f:
                json.dump({'branches': list(coverage.values())}, f)
            out = os.path.join(d, 'goals.csv')
            r = subprocess.run([sys.executable, os.path.join(SRC, 'report.py'), bmap, cov, '--mode', 'testcov',
                                '--source', os.path.join(d, name), '--csv', out, '--output', os.path.join(d, 'x.html')],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('TestCov goals: 2/3 (66.7%)', r.stdout)
            with open(out) as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[-1], ['SUMMARY', '', '', '', '2/3 goals (66.7%)'])
            self.assertEqual([row[4] for row in rows[1:-1]], ['yes', 'yes', 'no'])
            self.assertFalse(os.path.exists(os.path.join(d, 'x.html')))   # testcov mode writes only the CSV


if __name__ == '__main__':
    unittest.main()
