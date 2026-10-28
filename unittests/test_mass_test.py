"""scripts/batch/mass_test.py end to end on a small fake benchmark tree with a fake Sikraken.

Nothing here touches ~/benchmarks or ~/sikraken. The fake sv-benchmarks tree holds a few
programs from tests/ (one per status the driver can reach without the real Sikraken); the
fake bin/sikraken.sh writes a 2-test suite, or fails like the parser (FAKE_PARSE_FAIL in
the file), or hangs with a child process (FAKE_SLEEP) so the timeout must kill the group.
The real c2obra.sh, instrument.py, gcc and run_tests.py are used.

Run from the repo root:  python3 -m unittest unittests.test_mass_test -v
"""
import csv, glob, json, os, re, shutil, signal, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, '..', 'tests')   # test inputs (unittests/ holds the code)
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'scripts', 'batch'))
sys.path.insert(0, HERE)
import stages as S
import test_c2obra_sh as TC

PY = os.path.join(REPO, 'venv', 'bin', 'python3')
if not os.path.exists(PY):
    PY = sys.executable
DRIVER = os.path.join(REPO, 'scripts', 'batch', 'mass_test.py')

FAKE_SIKRAKEN = r'''#!/usr/bin/env bash
# Fake Sikraken (same arguments and output layout as the real one).
echo "$*" >> "$(dirname "$0")/../calls.txt"
f="${@: -1}"; name="$(basename "${f%.*}")"
out="$(dirname "$0")/../sikraken_output/$name"
mkdir -p "$out"
if grep -q FAKE_PARSE_FAIL "$f"; then
    echo "Sikraken from ./bin/sikraken.sh says: $(dirname "$0")/call_parser.sh $f -m64"
    echo "Fake parser: syntax error near '#' at line 1"
    echo "Sikraken ERROR from $(dirname "$0")/call_parser.sh: error code 1, sikraken_parser failed on x"
    echo "Sikraken ERROR from ./bin/sikraken.sh: error code 1, parser failed on: y"
    exit 1
fi
if grep -q FAKE_NO_TESTS "$f"; then
    mkdir -p "$out/test-suite"
    exit 0
fi
if grep -q FAKE_SLEEP "$f"; then
    sleep 300 &
    echo $! > "$(dirname "$0")/../sleep.pid"
    wait
fi
mkdir -p "$out/test-suite"
echo '<testcase><input>4</input><input>2</input></testcase>'  > "$out/test-suite/test_input-1.xml"
echo '<testcase><input>-1</input><input>3</input></testcase>' > "$out/test-suite/test_input-2.xml"
'''

# __VERIFIER_nondet_pointer has no stub (Sikraken rejects it too): a link error
NOSTUB_C = r'''extern void *__VERIFIER_nondet_pointer(void);
int main(void) { void *x = __VERIFIER_nondet_pointer(); if (x) return 1; return 0; }
'''
ABORT_C = r'''#include <stdlib.h>
extern int __VERIFIER_nondet_int(void);
int main(void) { int x = __VERIFIER_nondet_int(); if (x > 0) abort(); return 0; }
'''
INC_C = '#include "inc.h"\n' + TC.NONDET_C.replace('#include <stdio.h>', '#include <stdio.h>\n#define UNUSED INC_ONE')
INC_H = '#define INC_ONE 1\n'
# busybox <ctype.h>: a ?: in an enum value is not a decision (constant expression, no cover())
ENUM_C = 'enum { A = ((0) < 8 ? 1 : 2) };\nint main(void) { int x = A; if (x > 0) return 0; return 1; }\n'


def build_tree(root):
    """Fake sv-benchmarks + sample.csv + Sikraken under root. Returns {name: row}."""
    sv = os.path.join(root, 'sv-benchmarks')
    defs = os.path.join(TESTS, 'definition')

    def put(rel, text):
        p = os.path.join(sv, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(text)

    def read(p):
        with open(p) as f:
            return f.read()

    marked = subprocess.run(['gcc', '-E', os.path.join(defs, 'd07_for_infinite.c')],
                            capture_output=True, text=True, check=True).stdout
    tasks = {
        # name: (category, dir/stem, ext, content, data model)
        'plain':    ('Loops', 'loops/plain', '.c', read(os.path.join(defs, 'd01_if.c')), 'LP64'),
        'tree_a':   ('Loops', 'loops/tree-4', '.c', TC.NONDET_C, 'LP64'),
        'tree_b':   ('Heap', 'heap/tree-4', '.c', TC.NONDET_C, 'LP64'),
        'marked':   ('Arrays', 'arr/marked', '.i', marked, 'LP64'),
        'xmacro':   ('ECA', 'eca/xmacro', '.c', read(os.path.join(TESTS, 'corpusC', 'c07_xmacro_switch.c')), 'LP64'),
        'floats':   ('Floats', 'floats/m', '.c', TC.LIBM_C, 'LP64'),
        'nostub':   ('Combinations', 'comb/nostub', '.c', NOSTUB_C, 'LP64'),
        'parse':    ('Hardness', 'hard/parse', '.c', '/* FAKE_PARSE_FAIL */\n' + TC.NONDET_C, 'LP64'),
        'missing':  ('XCSP', 'x/missing', '.c', None, 'LP64'),
        'sleep':    ('Sequentialized', 'seq/sleep', '.c', '/* FAKE_SLEEP */\n' + TC.NONDET_C, 'LP64'),
        'inc':      ('SoftwareSystems-BusyBox', 'bb/inc', '.c', INC_C, 'LP64'),
        'notests':  ('ProductLines', 'pl/notests', '.c', '/* FAKE_NO_TESTS */\n' + TC.NONDET_C, 'LP64'),
        'abort':    ('Hardness', 'hard/abort', '.c', ABORT_C, 'LP64'),
        'enum':     ('SoftwareSystems-BusyBox', 'bb/enum', '.c', ENUM_C, 'LP64'),
    }
    if TC.can_build_m32():
        tasks['m32'] = ('Loops', 'loops/m32', '.c', TC.NONDET_C, 'ILP32')
    put('c/bb/inc.h', INC_H)
    rows = {}
    for name, (cat, stem, ext, text, dm) in tasks.items():
        if text is not None:
            put(f'c/{stem}{ext}', text)
        rows[name] = {'category': cat, 'yml_path': f'c/{stem}.yml', 'input_file': f'c/{stem}{ext}',
                      'extension': ext, 'data_model': dm}
    with open(os.path.join(root, 'sample.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['category', 'yml_path', 'input_file', 'extension', 'data_model'])
        w.writeheader()
        w.writerows(rows.values())
    sik = os.path.join(root, 'sik')
    os.makedirs(os.path.join(sik, 'bin'))
    with open(os.path.join(sik, 'bin', 'sikraken.sh'), 'w') as f:
        f.write(FAKE_SIKRAKEN)
    os.chmod(os.path.join(sik, 'bin', 'sikraken.sh'), 0o755)
    for r in rows.values():
        r['id'] = S.task_id(r['yml_path'])
    return rows


def driver(root, *args, **popen):
    cmd = [PY, DRIVER, '--sample', os.path.join(root, 'sample.csv'), '--runs-dir', os.path.join(root, 'runs'),
           '--sikraken-dir', os.path.join(root, 'sik'), *args]
    if popen:
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **popen)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


def run_dir(root):
    (d,) = glob.glob(os.path.join(root, 'runs', '*'))
    return d


def results(rd):
    with open(os.path.join(rd, 'results.csv'), newline='') as f:
        rows = list(csv.DictReader(f))
    return {r['id']: r for r in rows}


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    with open(f'/proc/{pid}/stat') as f:          # a zombie has exited
        return f.read().split()[2] != 'Z'


class FullBatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        cls.rows = build_tree(cls.root)
        cls.proc = driver(cls.root, '--name', 'mini', '--sikraken-timeout', '3')
        cls.rd = run_dir(cls.root)
        cls.res = results(cls.rd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)

    def r(self, name):
        return self.res[self.rows[name]['id']]

    def detail(self, name):
        return json.loads(self.r(name)['detail'])

    def test_driver_exit_and_csv(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stdout + self.proc.stderr)
        with open(os.path.join(self.rd, 'results.csv')) as f:
            self.assertEqual(f.readline().strip().split(','), S.FIELDS)
        self.assertEqual(len(self.res), len(self.rows))

    def test_statuses(self):
        want = {'plain': 'ok', 'tree_a': 'ok', 'tree_b': 'ok', 'marked': 'ok', 'xmacro': 'pairing_error',
                'floats': 'ok', 'nostub': 'compile_error', 'parse': 'sikraken_parse',
                'missing': 'input_missing', 'sleep': 'sikraken_timeout', 'inc': 'ok', 'm32': 'ok',
                'notests': 'no_tests', 'abort': 'partial', 'enum': 'ok'}
        got = {n: self.r(n)['status'] for n in self.rows}
        self.assertEqual(got, {n: want[n] for n in self.rows})

    def test_same_basename_two_tasks(self):
        self.assertNotEqual(self.rows['tree_a']['id'], self.rows['tree_b']['id'])
        for n in ('tree_a', 'tree_b'):
            self.assertEqual((self.r(n)['sikraken_tests'], self.r(n)['edges_covered'], self.r(n)['edges_total']),
                             ('2', '4', '4'))

    def test_coverage_columns_come_from_edge_coverage(self):
        r = self.r('plain')             # d01: 2 decisions, 3 of 4 edges (tests/definition/expected.csv)
        self.assertEqual((r['edges_covered'], r['edges_total'], r['pct'], r['decisions']), ('3', '4', '75.0', '2'))
        self.assertEqual(r['sikraken_tests'], '')

    def test_skipped_decisions_reported(self):
        r = self.r('enum')
        self.assertEqual((r['skipped_outside_function'], r['skipped_macro'], r['decisions']), ('1', '0', '1'))
        self.assertEqual(self.r('plain')['skipped_outside_function'], '0')

    def test_markers_cleaned(self):
        self.assertEqual(self.r('marked')['cleaned_markers'], '1')
        self.assertGreater(self.detail('marked')['marker_lines_blanked'], 0)
        self.assertTrue(glob.glob(os.path.join(self.rd, 'tasks', self.rows['marked']['id'], 'src', '*.i')))

    def test_compile_error_detail(self):
        r, d = self.r('nostub'), self.detail('nostub')
        self.assertEqual((r['stage'], d['missing_symbols']), ('compile', ['__VERIFIER_nondet_pointer']))
        self.assertEqual(r['edges_total'], '2')          # map exists, nothing ran
        self.assertEqual(r['edges_covered'], '')

    def test_sikraken_parse_detail(self):
        r, d = self.r('parse'), self.detail('parse')
        self.assertEqual(d['parser_error'], "Fake parser: syntax error near '#' at line 1")
        self.assertEqual(d['after_sikraken_failure']['c2obra_status'], 'ok')
        self.assertEqual((r['stage'], r['edges_total'], r['edges_covered']), ('sikraken', '4', ''))

    def test_no_tests(self):
        r, d = self.r('notests'), self.detail('notests')
        self.assertEqual((r['stage'], r['sikraken_tests'], r['nondet']), ('done', '0', 'True'))
        self.assertEqual(d['reason'], 'nondet file, Sikraken wrote no test')
        self.assertEqual(r['edges_total'], '4')

    def test_signal_recorded(self):
        d = self.detail('abort')          # fake suite: 4 (abort) and -1
        self.assertEqual(d['run_signals'], {'test_input-1.xml': 'SIGABRT'})
        self.assertEqual(d['reason'], 'some test runs did not pass')
        log = open(os.path.join(self.rd, 'tasks', self.rows['abort']['id'], 'log.txt')).read()
        self.assertIn('[test_input-1.xml] ended by SIGABRT (exit code -6)', log)

    def test_step_timestamps(self):
        d = self.detail('tree_a')
        self.assertEqual(set(d['step_seconds']), {'instrument', 'compile', 'run', 'report'})
        self.assertTrue(all(v >= 0 for v in d['step_seconds'].values()))
        with open(os.path.join(self.rd, 'tasks', self.rows['tree_a']['id'], 'log.txt')) as f:
            log = f.read()
        for marker in ('[driver] === prepare ===', '[driver] === sikraken ===', '=== Step 1: Instrument ===',
                       '=== Step 2: Compile ===', '=== Step 3: Run Tests ===', '=== Step 4: Report ==='):
            self.assertRegex(log, r'\[\d\d:\d\d:\d\d\.\d{3} \+\d+\.\d{3}s\] ' + re.escape(marker))

    def test_summary_coverage_filter(self):
        with open(os.path.join(self.rd, 'summary.txt')) as f:
            text = f.read()
        counted = [n for n in self.rows if S.counts_for_coverage(json.load(open(
            os.path.join(self.rd, 'tasks', self.rows[n]['id'], 'result.json'))))]
        self.assertNotIn('notests', counted)
        self.assertIn('abort', counted)
        self.assertIn(f'Edges over {len(counted)} ok+partial tasks with >= 1 Sikraken test or no nondet', text)
        self.assertIn('  SIGABRT         1 / 1', text)

    def test_timeout_kills_process_group(self):
        with open(os.path.join(self.root, 'sik', 'sleep.pid')) as f:
            self.assertFalse(alive(int(f.read())))

    def test_floats_note_and_headers(self):
        self.assertNotIn('notes', self.detail('floats'))     # float stubs read inputs now
        self.assertEqual(self.detail('inc')['headers_copied'], 1)

    def test_data_model_reaches_sikraken(self):
        with open(os.path.join(self.root, 'sik', 'calls.txt')) as f:
            calls = f.read().splitlines()
        self.assertTrue(all(' -m64 ' in c for c in calls if 'm32' not in c))
        if 'm32' in self.rows:
            self.assertTrue(any(' -m32 ' in c and 'loops__m32' in c for c in calls))

    def test_cleanup(self):
        self.assertEqual(glob.glob(os.path.join(self.root, 'sik', 'sikraken_output', '*')), [])
        self.assertEqual(glob.glob(os.path.join(self.rd, 'tasks', '*', 'out', '*_test')), [])
        ok_out = os.path.join(self.rd, 'tasks', self.rows['tree_a']['id'], 'out')
        self.assertEqual(glob.glob(os.path.join(ok_out, '*_inst.c')), [])
        self.assertTrue(glob.glob(os.path.join(ok_out, '*_branch_map.json')))
        failed = os.path.join(self.rd, 'tasks', self.rows['nostub']['id'], 'out')
        self.assertTrue(glob.glob(os.path.join(failed, '*_inst.c')))

    def test_summary_and_run_json(self):
        with open(os.path.join(self.rd, 'summary.txt')) as f:
            text = f.read()
        self.assertIn('    1  __VERIFIER_nondet_pointer', text)
        self.assertNotIn('floats_stub_unfixed', text)
        with open(os.path.join(self.rd, 'run.json')) as f:
            inv = json.load(f)['invocations'][0]
        self.assertEqual(len(inv['c2obra_commit']), 40)
        self.assertEqual(inv['timeouts']['sikraken'], 3)


class DryRunPilot(unittest.TestCase):
    def test_pilot_dry_run_creates_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            rows = build_tree(root)
            p = driver(root, '--name', 'p', '--pilot', '8', '--dry-run')
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            lines = p.stdout.strip().splitlines()
            self.assertTrue(lines[-1].startswith('8 tasks, 8 categories'), lines[-1])
            picked = {l.split(',')[0] for l in lines[:-1]}
            self.assertNotIn(rows['missing']['id'], picked)          # input not on disk
            self.assertIn(rows['marked']['id'], picked)              # the only cleaned .i
            self.assertFalse(os.path.exists(os.path.join(root, 'runs')))
            again = driver(root, '--name', 'p', '--pilot', '8', '--dry-run')
            self.assertEqual(again.stdout, p.stdout)


class Resume(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        rows = build_tree(self.root)
        keep = ['plain', 'xmacro', 'tree_a']
        with open(os.path.join(self.root, 'sample.csv'), newline='') as f:
            all_rows = list(csv.DictReader(f))
        with open(os.path.join(self.root, 'sample.csv'), 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0]))
            w.writeheader()
            w.writerows(r for r in all_rows if r['yml_path'] in {rows[k]['yml_path'] for k in keep})
        self.ids = {k: rows[k]['id'] for k in keep}

    def tearDown(self):
        shutil.rmtree(self.root)

    def result_mtime(self, rd, name):
        return os.stat(os.path.join(rd, 'tasks', self.ids[name], 'result.json')).st_mtime_ns

    def test_limit_then_resume_retry_and_incomplete(self):
        p = driver(self.root, '--name', 'r', '--limit', '2')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        rd = run_dir(self.root)
        self.assertEqual(len(results(rd)), 2)
        # sample order: plain, tree_a, xmacro. tasks.txt keeps the limited selection of the
        # new run; widen it to all three
        with open(os.path.join(rd, 'tasks.txt'), 'a') as f:
            f.write(self.ids['xmacro'] + '\n')
        before = {n: self.result_mtime(rd, n) for n in ('plain', 'tree_a')}
        p = driver(self.root, '--run-dir', rd)
        self.assertIn('1 to run', p.stdout)
        self.assertEqual(len(results(rd)), 3)
        self.assertEqual({n: self.result_mtime(rd, n) for n in before}, before)   # not run again

        os.remove(os.path.join(rd, 'tasks', self.ids['plain'], 'result.json'))  # interrupted attempt
        p = driver(self.root, '--run-dir', rd, '--retry-status', 'pairing_error')
        self.assertIn('2 to run (2 moved to _incomplete/)', p.stdout)
        moved = sorted(os.path.basename(d).split('.')[0] for d in glob.glob(os.path.join(rd, '_incomplete', '*')))
        self.assertEqual(moved, sorted([self.ids['plain'], self.ids['xmacro']]))
        self.assertEqual(results(rd)[self.ids['xmacro']]['status'], 'pairing_error')
        self.assertEqual(len(results(rd)), 3)

    def test_ctrl_c(self):
        with open(os.path.join(self.root, 'sv-benchmarks', 'c', 'loops', 'tree-4.c'), 'a') as f:
            f.write('/* FAKE_SLEEP */\n')
        p = driver(self.root, '--name', 'c', '--sikraken-timeout', '120', start_new_session=False)
        pid_file = os.path.join(self.root, 'sik', 'sleep.pid')
        deadline = time.time() + 120
        while not os.path.exists(pid_file) and time.time() < deadline:
            time.sleep(0.2)
        time.sleep(0.5)
        p.send_signal(signal.SIGINT)
        out, _ = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 130, out)
        rd = run_dir(self.root)
        res = results(rd)
        self.assertEqual(set(res), {self.ids['plain']})     # tree_a interrupted, xmacro not started
        self.assertFalse(os.path.exists(os.path.join(rd, 'tasks', self.ids['tree_a'], 'result.json')))
        with open(pid_file) as f:
            self.assertFalse(alive(int(f.read())))


if __name__ == '__main__':
    unittest.main()
