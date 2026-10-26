"""batch/stages.py: task ids, marker cleaning, stage classification, pilot, resume, results.

The c2obra.sh logs used for classification are real: c2obra.sh is run in the sandbox of
test_c2obra_sh.py (pairing error, link error, success). The Sikraken logs are built from the
echo lines of sikraken.sh / call_parser.sh; the parser's own error text is made up, because
the real sikraken_parser.exe output has not been captured yet (do that in the pilot).

Run from the repo root:  python3 -m unittest tests.test_stages -v
"""
import contextlib, io, json, os, random, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'batch'))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)
import stages as S
import instrument as I
import test_c2obra_sh as TC

TASK_LIST = os.environ.get('C2OBRA_TASK_LIST')   # e.g. ~/benchmarks/cover-branches-tasks.txt


class TaskIds(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(S.task_id('c/array-cav19/array_init_var_plus_ind.yml'),
                         'array-cav19__array_init_var_plus_ind')
        self.assertEqual(S.task_id('c/ldv-linux-4.2-rc1/linux-4.2-rc1.tar.xz-08_1a.cil.out.yml'),
                         'ldv-linux-4_2-rc1__linux-4_2-rc1_tar_xz-08_1a_cil_out')
        self.assertEqual(S.task_id('c/hardware-verification-bv/btor2c-lazyMod.x+y.yml'),
                         'hardware-verification-bv__btor2c-lazyMod_x_y')

    def test_same_basename_in_two_directories(self):
        rows = S.assign_ids([{'yml_path': 'c/loops/tree-4.yml'}, {'yml_path': 'c/heap/tree-4.yml'},
                             {'yml_path': 'c/loops/tree-4-1.yml'}])
        self.assertEqual(len({r['id'] for r in rows}), 3)

    def test_collision_is_an_error(self):
        with self.assertRaises(ValueError):
            S.assign_ids([{'yml_path': 'c/a/x.y.yml'}, {'yml_path': 'c/a/x_y.yml'}])
        with self.assertRaises(ValueError):
            S.assign_ids([{'yml_path': 'c/a/x.yml'}, {'yml_path': 'c/a/x.yml'}])

    @unittest.skipUnless(TASK_LIST and os.path.exists(TASK_LIST), 'set C2OBRA_TASK_LIST to the task list')
    def test_all_cover_branches_tasks(self):
        with open(TASK_LIST) as f:
            rows = [{'yml_path': l.strip()} for l in f if l.strip()]
        S.assign_ids(rows)                                   # raises on a collision
        self.assertTrue(all(re_safe(r['id']) for r in rows))


def re_safe(s):
    return all(c.isalnum() and c.isascii() or c in '_-' for c in s)


class LineMarkers(unittest.TestCase):
    def test_only_when_first_line_is_a_marker(self):
        text = 'int x;\n# 1 "a.c"\nint y;\n'
        self.assertEqual(S.strip_line_markers(text), (text, 0))

    def test_markers_blanked_line_numbers_kept(self):
        text = ('# 0 "a.c"\n# 0 "<built-in>"\n# 1 "/usr/include/stdio.h" 1 3 4\nint x;\n'
                '# 12 "a.c" 2\n#pragma once\n#include "h.h"\n# define N 3\n#line 5 "b.c"\n'
                '#  1 "not-gcc-format"\n# 7 "we\\"ird.c" 2\nreturn;\n')
        new, n = S.strip_line_markers(text)
        self.assertEqual(n, 5)
        old_lines, new_lines = text.split('\n'), new.split('\n')
        self.assertEqual(len(new_lines), len(old_lines))
        for o, m in zip(old_lines, new_lines):
            self.assertEqual(m, '' if o in ('# 0 "a.c"', '# 0 "<built-in>"', '# 1 "/usr/include/stdio.h" 1 3 4',
                                            '# 12 "a.c" 2', '# 7 "we\\"ird.c" 2') else o)

    def test_crlf_kept(self):
        self.assertEqual(S.strip_line_markers('# 1 "a.c"\r\nint x;\r\n'), ('\r\nint x;\r\n', 1))

    def test_cleaned_d15_instruments(self):
        """gcc -E puts markers inside assert()'s expansion and pairing stops
        (test_preprocessed_input); after cleaning it instruments like gcc -E -P (4 decisions)."""
        with tempfile.TemporaryDirectory() as d:
            i = os.path.join(d, 'd15.i')
            subprocess.run(['gcc', '-E', os.path.join(HERE, 'definition', 'd15_macros.c'), '-o', i], check=True)
            with open(i) as f:
                new, n = S.strip_line_markers(f.read())
            self.assertGreater(n, 0)
            with open(i, 'w') as f:
                f.write(new)
            with contextlib.redirect_stdout(io.StringIO()):
                I.instrument_file(i, os.path.join(d, 'd15_inst.c'), flags=[])
            with open(os.path.join(d, 'd15_inst_branch_map.json')) as f:
                self.assertEqual(len(json.load(f)['branches']), 4)


SIK_HEAD = ('Sikraken from ./bin/sikraken.sh says: /s/bin/call_parser.sh ../runs/t/src/c2b__x.i -m32\n'
            'Sikraken /s/bin/call_parser.sh says: SIKRAKEN_INSTALL_DIR is /s/bin/..\n')


class ClassifySikraken(unittest.TestCase):
    def test_parse_error(self):
        log = (SIK_HEAD + 'Parse error: unexpected token "#" at line 1\n\n'   # made-up parser text
               'Sikraken ERROR from /s/bin/call_parser.sh: error code 1, sikraken_parser failed on x\n'
               'Sikraken ERROR from ./bin/sikraken.sh: error code 1, parser failed on: y\n')
        status, detail = S.classify_sikraken(1, False, log, None)
        self.assertEqual(status, 'sikraken_parse')
        self.assertEqual(detail['parser_error'], 'Parse error: unexpected token "#" at line 1')

    def test_gcc_preprocess_failure_is_parse_stage(self):
        log = SIK_HEAD + 'Sikraken ERROR from /s/bin/call_parser.sh: error code 1, gcc failed on gcc -E\n'
        self.assertEqual(S.classify_sikraken(22, False, log, None)[0], 'sikraken_parse')

    def test_eclipse_error(self):
        log = SIK_HEAD + 'Sikraken ERROR from ./bin/sikraken.sh: error code 3, call to ECLiPSe failed on: e\n'
        status, detail = S.classify_sikraken(3, False, log, None)
        self.assertEqual(status, 'sikraken_error')
        self.assertIn('ECLiPSe', detail['sikraken_error'])

    def test_exit_0_without_suite(self):            # sikraken.sh maps 137 to 0
        self.assertEqual(S.classify_sikraken(0, False, 'Like tears in rain...\n', None)[0], 'sikraken_error')

    def test_timeout_and_ok(self):
        self.assertEqual(S.classify_sikraken(-9, True, '', None)[0], 'sikraken_timeout')
        self.assertEqual(S.classify_sikraken(0, False, '', 0), (None, {}))
        self.assertEqual(S.classify_sikraken(0, False, '', 12), (None, {}))


class ClassifyC2obraRealLogs(unittest.TestCase):
    """Logs of the real c2obra.sh, run in the test_c2obra_sh sandbox."""

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        TC.make_sandbox(cls.d)
        shutil.copy(os.path.join(HERE, 'corpusC', 'c07_xmacro_switch.c'), os.path.join(cls.d, 'in'))
        with open(os.path.join(cls.d, 'in', 'm.c'), 'w') as f:
            f.write(TC.LIBM_C)
        cls.pairing = TC.run_c2obra(cls.d, 'in/c07_xmacro_switch.c', OUT_DIR='a')
        cls.link = TC.run_c2obra(cls.d, 'in/m.c', OUT_DIR='b')
        cls.good = TC.run_c2obra(cls.d, 'in/m.c', OUT_DIR='c', LDLIBS='-lm')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d)

    def test_pairing_error(self):
        status, stage, detail = S.classify_c2obra(self.pairing[0], False, self.pairing[1])
        self.assertEqual((status, stage), ('pairing_error', 'instrument'))
        self.assertIn('could not be paired', detail['error'])

    def test_link_error_lists_missing_symbols(self):
        status, stage, detail = S.classify_c2obra(self.link[0], False, self.link[1])
        self.assertEqual((status, stage), ('compile_error', 'compile'))
        self.assertEqual(sorted(detail['missing_symbols']), ['cbrt', 'log10'])

    def test_success(self):
        self.assertEqual(S.classify_c2obra(self.good[0], False, self.good[1]), (None, 'done', {}))


class ClassifyC2obra(unittest.TestCase):
    def test_clang_error(self):
        log = '=== Step 1: Instrument ===\n❌ Error: Clang reported 2 error(s) in x.i; the scan would be incomplete.\n'
        self.assertEqual(S.classify_c2obra(1, False, log)[0], 'clang_error')

    def test_other_instrument_error(self):
        log = '=== Step 1: Instrument ===\n❌ Error: Expected a .c or .i file\n'
        self.assertEqual(S.classify_c2obra(1, False, log)[:2], ('instrument_error', 'instrument'))

    def test_missing_symbols_first_five_distinct(self):
        log = '=== Step 2: Compile ===\n' + ''.join(
            f"/usr/bin/ld: x.c:(.text+0x{i:x}): undefined reference to `{s}'\n"
            for i, s in enumerate(['a', 'b', 'a', 'c', 'd', 'b', 'e', 'f', 'g']))
        self.assertEqual(S.missing_symbols(log), ['a', 'b', 'c', 'd', 'e'])
        self.assertEqual(S.missing_symbols("undefined reference to ‘q’"), ['q'])

    def test_compile_syntax_error(self):
        log = "=== Step 2: Compile ===\nout/x_inst.c:3:1: error: expected ';' before '}' token\n"
        status, stage, detail = S.classify_c2obra(1, False, log)
        self.assertEqual(status, 'compile_error')
        self.assertEqual(detail['missing_symbols'], [])
        self.assertIn("expected ';'", detail['first_error'])

    def test_run_stage(self):
        log = '=== Step 1: Instrument ===\n=== Step 2: Compile ===\n=== Step 3: Run Tests ===\n'
        self.assertEqual(S.classify_c2obra(1, False, log)[:2], ('run_crash', 'run'))
        self.assertEqual(S.classify_c2obra(-9, True, log)[:2], ('run_timeout', 'run'))

    def test_timeout_outside_run(self):
        log = '=== Step 1: Instrument ===\n=== Step 2: Compile ===\n'
        self.assertEqual(S.classify_c2obra(-9, True, log)[:2], ('tool_timeout', 'compile'))
        self.assertEqual(S.classify_c2obra(-9, True, '')[:2], ('tool_timeout', 'instrument'))


def cov(**runs):
    return {'summary': {'test_run_statuses': {'pass': 0, 'partial': 0, 'timeout': 0, 'crash': 0, **runs}},
            'branches': []}


class ClassifyRun(unittest.TestCase):
    def test_statuses(self):
        self.assertEqual(S.classify_run(cov(**{'pass': 3}), True, 3)[0], 'ok')
        self.assertEqual(S.classify_run(cov(**{'pass': 3}), False, None)[0], 'ok')
        self.assertEqual(S.classify_run(cov(**{'pass': 3}), True, 0)[0], 'no_tests')    # no Sikraken test
        self.assertEqual(S.classify_run(cov(**{'pass': 1}), True, None)[0], 'no_tests')
        self.assertEqual(S.classify_run(cov(**{'pass': 2, 'crash': 1}), True, 3)[0], 'partial')
        self.assertEqual(S.classify_run(cov(crash=3), True, 3)[0], 'run_crash')       # real tests, all crash
        self.assertEqual(S.classify_run(cov(timeout=3), True, 3)[0], 'run_timeout')
        self.assertEqual(S.classify_run(cov(crash=1), False, None)[0], 'run_crash')   # no nondet call
        self.assertEqual(S.classify_run(None, True, 3)[0], 'run_crash')
        self.assertEqual(S.classify_run(None, True, 0)[0], 'run_crash')               # no coverage JSON at all

    def test_no_tests_wins_over_a_crash_of_the_no_input_run(self):
        # array-multidimensional__min-3-n-u (2026-10-20): 0 Sikraken tests, no_inputs run SIGSEGV
        status, detail = S.classify_run(cov(crash=1), True, 0)
        self.assertEqual(status, 'no_tests')
        self.assertEqual(detail['test_run_statuses']['crash'], 1)
        self.assertEqual(S.classify_run(cov(timeout=1), True, 0)[0], 'no_tests')
        self.assertEqual(S.classify_run(cov(crash=1), True, None)[0], 'no_tests')


def synthetic_rows():
    rows = []
    for c in range(12):
        for ext in ('.c', '.i'):
            for dm in ('ILP32', 'LP64'):
                for k in range(3):
                    rows.append({'category': f'Cat{c:02d}', 'extension': ext, 'data_model': dm,
                                 'yml_path': f'c/cat{c}/t{k}{ext[1]}{dm}.yml'})
    return S.assign_ids(rows)


class Pilot(unittest.TestCase):
    def test_mix_and_determinism(self):
        rows = synthetic_rows()
        a = S.pick_pilot(rows)
        shuffled = rows[:]
        random.Random(1).shuffle(shuffled)
        self.assertEqual([r['id'] for r in S.pick_pilot(shuffled)], [r['id'] for r in a])
        self.assertEqual(len(a), 20)
        self.assertGreaterEqual(len({r['category'] for r in a}), 10)
        cells = {(r['extension'], r['data_model']) for r in a}
        self.assertEqual(len(cells), 4)
        self.assertTrue(all(sum(1 for r in a if (r['extension'], r['data_model']) == c) == 5 for c in cells))

    def test_short_cell_is_filled_by_others(self):
        rows = [r for r in synthetic_rows() if not (r['extension'] == '.i' and r['data_model'] == 'LP64')]
        rows += [r for r in synthetic_rows() if r['extension'] == '.i' and r['data_model'] == 'LP64'][:2]
        a = S.pick_pilot(rows)
        self.assertEqual(len(a), 20)
        self.assertEqual(sum(1 for r in a if r['extension'] == '.i' and r['data_model'] == 'LP64'), 2)

    def test_required_tags_swapped_in(self):
        rows = synthetic_rows()
        special = {rows[7]['id']: {'cleaned'}, rows[100]['id']: {'no_nondet'}}
        a = S.pick_pilot(rows, props=lambda r: special.get(r['id'], set()))
        ids = {r['id'] for r in a}
        self.assertTrue(set(special) <= ids)
        self.assertEqual(len(a), 20)

    def test_too_few_categories_is_an_error(self):
        with self.assertRaises(ValueError):
            S.pick_pilot(synthetic_rows(), n=5, min_categories=10)


class Selection(unittest.TestCase):
    def test_only_list_and_limit(self):
        rows = synthetic_rows()
        only = S.read_only_list(f"# pilot\n{rows[3]['id']}\n\n{rows[5]['yml_path']}  # by path\n")
        self.assertEqual([r['id'] for r in S.filter_rows(rows, only=only)], [rows[3]['id'], rows[5]['id']])
        self.assertEqual(len(S.filter_rows(rows, limit=7)), 7)

    def test_resume(self):
        rows = synthetic_rows()[:5]
        with tempfile.TemporaryDirectory() as d:
            def result(i, status):
                os.makedirs(os.path.join(d, rows[i]['id']))
                S.atomic_write(os.path.join(d, rows[i]['id'], 'result.json'), json.dumps({'status': status}))
            result(0, 'ok')
            result(1, 'compile_error')
            os.makedirs(os.path.join(d, rows[2]['id']))                 # interrupted: no result.json
            os.makedirs(os.path.join(d, rows[3]['id']))
            with open(os.path.join(d, rows[3]['id'], 'result.json'), 'w') as f:
                f.write('{"status": "o')                                 # half-written
            run, retire = S.select_tasks(rows, d)
            self.assertEqual([r['id'] for r in run], [rows[i]['id'] for i in (2, 3, 4)])
            self.assertEqual(retire, [os.path.join(d, rows[i]['id']) for i in (2, 3)])
            run, retire = S.select_tasks(rows, d, retry_statuses={'compile_error'})
            self.assertEqual([r['id'] for r in run], [rows[i]['id'] for i in (1, 2, 3, 4)])
            self.assertIn(os.path.join(d, rows[1]['id']), retire)


class Results(unittest.TestCase):
    def result(self, **kw):
        base = {'id': 't', 'category': 'Loops', 'status': 'ok', 'stage': 'done', 'seconds': 1.0,
                'edges_covered': 3, 'edges_total': 4, 'cleaned_markers': 0, 'detail': {}}
        base.update(kw)
        return base

    def test_csv_row(self):
        row = S.csv_row(self.result(sikraken_tests=None, detail={'notes': ['example_note']}))
        self.assertEqual(list(row), S.FIELDS)
        self.assertEqual(row['sikraken_tests'], '')
        self.assertEqual(json.loads(row['detail']), {'notes': ['example_note']})

    def test_atomic_write_replaces(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'r.csv')
            S.atomic_write(p, 'a\n')
            S.atomic_write(p, 'b\n')
            with open(p) as f:
                self.assertEqual(f.read(), 'b\n')
            self.assertEqual(os.listdir(d), ['r.csv'])

    def test_summary(self):
        res = [self.result(id='a', seconds=5.0),
               self.result(id='b', status='compile_error', stage='compile', seconds=9.0, edges_total=None,
                           detail={'missing_symbols': ['__VERIFIER_nondet_ulong', 'x']}),
               self.result(id='c', status='compile_error', stage='compile', category='Floats',
                           detail={'missing_symbols': ['__VERIFIER_nondet_ulong'], 'notes': ['example_note']}),
               self.result(id='d', status='partial', edges_covered=1, edges_total=6, cleaned_markers=1)]
        text = S.summary(res, planned=6, wall_seconds=60)
        self.assertIn('4 finished of 6 planned (2 not done)', text)
        self.assertIn('    2  __VERIFIER_nondet_ulong', text)
        self.assertIn('    1  x', text)
        self.assertIn('Edges over 2 ok+partial tasks with >= 1 Sikraken test or no nondet '
                      '(sum of per-task edges.edge_coverage()): 4/10 = 40.0%', text)
        self.assertIn('Tasks with note example_note: 1', text)
        self.assertIn('Inputs with gcc line markers cleaned: 1', text)
        slow = text.split('10 slowest tasks:')[1].split('\n')[1]
        self.assertIn(' b', slow)

    def test_summary_per_task_coverage(self):
        # per task: 25%, 75%, 100%, and one with 0 edges (left out) -> median 75.0, mean 66.7
        res = [self.result(id='a', edges_covered=1, edges_total=4),
               self.result(id='b', edges_covered=3, edges_total=4),
               self.result(id='c', status='partial', edges_covered=1, edges_total=1),
               self.result(id='d', edges_covered=0, edges_total=0)]
        lines = S.summary(res, planned=4, wall_seconds=1).split('\n')
        i = next(k for k, l in enumerate(lines) if l.startswith('Edges over 4 '))
        self.assertTrue(lines[i].endswith(': 5/9 = 55.6%'))
        self.assertEqual(lines[i + 1], 'Per-task coverage over the same 4 tasks: '
                                       'median 75.0%, mean 66.7% (tasks with 0 edges left out: 1)')


ABORT_C = r'''#include <stdlib.h>
extern int __VERIFIER_nondet_int(void);
int main(void) { int x = __VERIFIER_nondet_int(); if (x > 0) abort(); return 0; }
'''


class RunSignals(unittest.TestCase):
    def test_real_run_tests_log(self):
        """run_tests.py on a binary that calls abort() for x > 0 (cov_runtime.c re-raises SIGABRT)."""
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, 'a.c')
            with open(c, 'w') as f:
                f.write(ABORT_C)
            inst = os.path.join(d, 'a_inst.c')
            with contextlib.redirect_stdout(io.StringIO()):
                I.instrument_file(c, inst, flags=[])
            src = os.path.join(HERE, '..', 'src')
            exe = os.path.join(d, 'a')
            subprocess.run(['gcc', '-w', inst, os.path.join(src, 'cov_runtime.c'),
                            os.path.join(src, 'verifier_stubs.c'), '-I', src, '-o', exe], check=True)
            suite = os.path.join(d, 'suite')
            os.makedirs(suite)
            for i, v in enumerate(['4', '-1'], 1):
                with open(os.path.join(suite, f'test_input-{i}.xml'), 'w') as f:
                    f.write(f'<testcase><input>{v}</input></testcase>')
            r = subprocess.run([sys.executable, os.path.join(src, 'run_tests.py'), exe, suite,
                                os.path.join(d, 'a_inst_branch_map.json')],
                               cwd=d, capture_output=True, text=True, timeout=120)
            signals, timeouts = S.run_signals(r.stdout)
            self.assertEqual(signals, {'test_input-1.xml': 'SIGABRT'})
            self.assertEqual(timeouts, [])
            self.assertIn('[test_input-1.xml] ended by SIGABRT (exit code -6)', r.stdout)

    def test_timeout_lines(self):
        log = '  ⚠️  [test_input-3] TIMED OUT after 35s — killed\n  ⚠️  [t9] ended by signal 77 (exit code -77)\n'
        self.assertEqual(S.run_signals(log), ({'t9': 'signal 77'}, ['test_input-3']))


class StepSeconds(unittest.TestCase):
    def test_split(self):
        marks = [('instrument', 10.0), ('compile', 12.5), ('run', 13.0), ('report', 20.0), ('done', 20.5)]
        self.assertEqual(S.step_seconds(marks, 21.0),
                         {'instrument': 2.5, 'compile': 0.5, 'run': 7.0, 'report': 0.5, 'done': 0.5})


class TimingRow(unittest.TestCase):
    def test_parse_is_split_off_the_instrument_step(self):
        r = {'id': 't', 'category': 'Loops', 'extension': '.c', 'status': 'ok', 'seconds': 12.0,
             'seconds_sikraken': 9.0, 'seconds_c2obra': 2.5,
             'detail': {'input_bytes': 1234, 'instrument_timing': {'parse': 0.15, 'instrument': 0.02},
                        'step_seconds': {'instrument': 0.4, 'compile': 1.2, 'run': 0.6, 'report': 0.3}}}
        row = S.timing_row(r)
        self.assertEqual(list(row), S.TIMING_FIELDS)
        self.assertEqual((row['sikraken'], row['parse'], row['instrument'], row['compile'], row['run'],
                          row['report'], row['c2obra'], row['total'], row['input_bytes']),
                         (9.0, 0.15, 0.25, 1.2, 0.6, 0.3, 2.5, 12.0, 1234))

    def test_stages_that_did_not_run_are_empty(self):
        # instrument.py stopped (no timing file): parse empty, instrument = whole step
        r = {'id': 't', 'status': 'pairing_error', 'seconds': 1.0, 'seconds_sikraken': None,
             'detail': {'step_seconds': {'instrument': 0.5}}}
        row = S.timing_row(r)
        self.assertEqual((row['sikraken'], row['parse'], row['instrument'], row['compile']), ('', '', 0.5, ''))


class CoverageFilter(unittest.TestCase):
    def test_counts_for_coverage(self):
        base = {'edges_total': 4, 'edges_covered': 2}
        yes = [dict(base, status='ok', nondet=True, sikraken_tests=3),
               dict(base, status='partial', nondet=True, sikraken_tests=1),
               dict(base, status='ok', nondet=False, sikraken_tests=None)]
        no = [dict(base, status='no_tests', nondet=True, sikraken_tests=0),
              dict(base, status='ok', nondet=True, sikraken_tests=0),
              dict(base, status='compile_error', nondet=False, sikraken_tests=None),
              dict(status='ok', nondet=False, sikraken_tests=None, edges_total=None)]
        self.assertTrue(all(S.counts_for_coverage(r) for r in yes))
        self.assertFalse(any(S.counts_for_coverage(r) for r in no))

    def test_summary_signal_table(self):
        res = [{'id': 'a', 'category': 'X', 'status': 'partial', 'stage': 'done', 'seconds': 1.0,
                'detail': {'run_signals': {'t1': 'SIGABRT', 't2': 'SIGABRT', 't3': 'SIGSEGV'}}},
               {'id': 'b', 'category': 'X', 'status': 'partial', 'stage': 'done', 'seconds': 1.0,
                'detail': {'run_signals': {'t1': 'SIGABRT'}}}]
        text = S.summary(res, planned=2, wall_seconds=1)
        self.assertIn('  SIGABRT         3 / 2', text)
        self.assertIn('  SIGSEGV         1 / 1', text)


if __name__ == '__main__':
    unittest.main()
