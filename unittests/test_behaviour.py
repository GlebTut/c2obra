"""Behaviour preservation (spec 5.5): original and instrumented program, same stdout and exit status.

Corpus: tests/corpusC/c*.c, tests/examples/*.c, tests/loop-simple/*.c, tests/loop-lit/*.c,
tests/definition/d*.c. Each program is instrumented with its flags from FLAGS (default none,
as in the other tests), the original and the instrumented copy are compiled with gcc
(test_definition.build_and_run) with the same flags, and both are run with no input (stdin
/dev/null) and a short timeout.

corpusC/c01..c14 have no main(): tests/corpusC/drivers/cNN_main.inc holds one, which is
appended to a copy of the file before the check (row "corpusC/cNN (with driver)").

Every program gets one row: PASS (same behaviour), FAIL (different, or the instrumented copy
does not compile) or SKIP with a reason (nondeterministic input, original does not compile,
original times out, or instrument.py stops with an error). Only a FAIL that is not listed in
KNOWN_FAIL fails the test.

The table is printed. With C2OBRA_BEHAVIOUR_MD=1 it is also written to
tests/behaviour_check_results.md:
    C2OBRA_BEHAVIOUR_MD=1 venv/bin/python3 -m unittest unittests.test_behaviour -v

Run from the repo root:  python3 -m unittest unittests.test_behaviour -v
"""
import contextlib, datetime, glob, importlib.metadata, io, os, re, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, '..', 'tests')   # test inputs (unittests/ holds the code)
SRC = os.path.join(HERE, '..', 'src')
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)
import instrument as I
from test_definition import build_and_run

CORPUS = ['corpusC/c*.c', 'examples/*.c', 'loop-simple/*.c', 'loop-lit/*.c', 'definition/d*.c']
TIMEOUT = 5                      # seconds per run
RESULTS_MD = os.path.join(TESTS, 'behaviour_check_results.md')
DRIVERS = os.path.join(TESTS, 'corpusC', 'drivers')

# -D flags per program, one check per flag list; the same flags go to instrument.py and gcc.
# As in test_pairing.py / test_clang_scan.py: c03 and c05 also with the define that selects
# their other #ifdef arm.
FLAGS = {
    'c03_ifdef_split_braces.c': [[], ['-DFAST']],
    'c05_flag_dependent.c':     [[], ['-DDEBUG']],
}

# FAILs that are known bugs in src/, not yet fixed. They stay FAIL in the table but do not fail
# the test; any other FAIL does. An entry that no longer FAILs fails the test, so the list is
# kept up to date when the bug is fixed.
KNOWN_FAIL = {
    'corpusC/c09 (with driver)': 'GNU case range `case 1 ... 5:` (tree-sitter-c 0.21.3 makes '
                                 '`... 5` an ERROR node, get_switch_cases() uses it as the value)',
}


def driver(path):
    """tests/corpusC/drivers/cNN_main.inc for tests/corpusC/cNN_*.c, or None."""
    if os.path.basename(os.path.dirname(path)) != 'corpusC':
        return None
    inc = os.path.join(DRIVERS, os.path.basename(path)[:3] + '_main.inc')
    return inc if os.path.exists(inc) else None


def corpus():
    """(row label, path, flags, driver .inc or None) for every check."""
    cases = []
    for g in CORPUS:
        for p in sorted(glob.glob(os.path.join(TESTS, g))):
            drv = driver(p)
            for flags in FLAGS.get(os.path.basename(p), [[]]):
                label = os.path.relpath(p, TESTS)
                if drv:
                    label = f"corpusC/{os.path.basename(p)[:3]} (with driver)"
                if flags:
                    label += ' ' + ' '.join(flags)
                cases.append((label, p, flags, drv))
    return cases


def first_line(text):
    return next((l.strip() for l in text.splitlines() if l.strip()), '')


def gcc_error(text):
    """The first compiler/linker error line of gcc's output, without the file path."""
    line = next((l for l in text.splitlines() if 'error' in l or 'undefined reference' in l), first_line(text))
    if 'undefined reference' in line:
        return line.strip().rsplit(': ', 2)[-1]
    return re.sub(r'^/\S*/', '', line.strip())          # drop the temp dir of the file name


def check_program(path, flags=(), drv=None):
    """(result, reason, detail) for one program; detail holds both runs on FAIL.
    drv: a .inc file appended to the copy (a main() for a file that has none)."""
    with open(path, errors='replace') as f:
        code = f.read()
    if drv:
        with open(drv) as f:
            code += '\n' + f.read()
    if '__VERIFIER_nondet' in code:
        return 'SKIP', 'nondeterministic input (__VERIFIER_nondet_*)', None
    name = os.path.basename(path)
    inc = ['-I', os.path.dirname(path)] + list(flags)   # local headers (c10); gcc and the scan
    with tempfile.TemporaryDirectory() as d:
        orig = os.path.join(d, name)
        with open(orig, 'w') as f:
            f.write(code)
        try:
            expected = build_and_run(d, orig, inc, timeout=TIMEOUT)
        except AssertionError as e:
            return 'SKIP', f'original does not compile: {gcc_error(str(e))}', None
        except subprocess.TimeoutExpired:
            return 'SKIP', f'timeout: original runs longer than {TIMEOUT} s', None
        inst = os.path.join(d, name[:-2] + '_inst.c')
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                I.instrument_file(orig, inst, flags=inc)
        except SystemExit:
            err = next((l for l in out.getvalue().splitlines() if l.startswith('❌')), 'exit')
            return 'SKIP', f'instrument.py stopped: {err[:120]}', None
        try:
            got = build_and_run(d, inst, inc + [os.path.join(SRC, 'cov_runtime.c'),
                                                os.path.join(SRC, 'verifier_stubs.c')], timeout=TIMEOUT)
        except AssertionError as e:
            return 'FAIL', f'instrumented copy does not compile: {gcc_error(str(e))}', {'error': str(e)}
        except subprocess.TimeoutExpired:
            got = ('timeout', '')
        if got != expected:
            return 'FAIL', 'different exit status or stdout', {'original': expected, 'instrumented': got}
        return 'PASS', '', None


def tool_versions():
    gcc = first_line(subprocess.run(['gcc', '--version'], capture_output=True, text=True).stdout)
    clang_bin = os.environ.get('C2OBRA_CLANG', 'clang')
    clang = first_line(subprocess.run([clang_bin, '--version'], capture_output=True, text=True).stdout)
    return {'gcc': gcc, f'{clang_bin} (resource dir for the scan)': clang,
            'libclang (Python, used by the scan)': importlib.metadata.version('libclang')}


def table(rows):
    lines = ['| program | result | reason |', '|---|---|---|']
    lines += [f"| {p} | {res} | {reason.replace('|', '/')} |" for p, res, reason, _ in rows]
    return '\n'.join(lines)


def summary_line(rows, counts):
    known = sum(1 for p, res, _, _ in rows if res == 'FAIL' and p in KNOWN_FAIL)
    return (f"PASS {counts['PASS']}, FAIL {counts['FAIL']} ({known} known bug), SKIP {counts['SKIP']} "
            f"(of {len(rows)} checks)")


def write_md(rows, counts, versions):
    with open(RESULTS_MD, 'w') as f:
        f.write('# Behaviour preservation on the corpus\n\n')
        f.write(f'Date: {datetime.date.today().isoformat()}. Written by `unittests/test_behaviour.py` '
                f'(`C2OBRA_BEHAVIOUR_MD=1`).\n\n')
        f.write('Original and instrumented program compiled with gcc, run with no input (stdin '
                f'`/dev/null`) and a {TIMEOUT} s timeout; stdout and exit status compared.\n\n')
        f.write('Tools:\n\n' + ''.join(f'- {k}: `{v}`\n' for k, v in versions.items()) + '\n')
        f.write(summary_line(rows, counts) + '\n\n')
        f.write(table(rows) + '\n')


class BehaviourPreserved(unittest.TestCase):
    def test_corpus(self):
        cases = corpus()
        self.assertTrue(cases)
        rows = []
        for label, p, flags, drv in cases:
            res, reason, detail = check_program(p, flags, drv)
            if res == 'FAIL' and label in KNOWN_FAIL:
                reason = f'known bug: {KNOWN_FAIL[label]}. {reason}'
            rows.append((label, res, reason, detail))
        counts = {k: sum(1 for r in rows if r[1] == k) for k in ('PASS', 'FAIL', 'SKIP')}
        print('\n' + table(rows))
        for label, res, _, detail in rows:
            if res == 'FAIL':
                print(f"FAIL {label}: {detail}")
        print(summary_line(rows, counts))
        if os.environ.get('C2OBRA_BEHAVIOUR_MD') == '1':
            write_md(rows, counts, tool_versions())

        self.assertEqual(len(rows), len(cases))                     # no program dropped
        for p, res, reason, _ in rows:
            self.assertIn(res, ('PASS', 'FAIL', 'SKIP'))
            if res == 'SKIP':
                self.assertTrue(reason, f'{p}: SKIP without a reason')
        fails = {p: (reason, detail) for p, res, reason, detail in rows
                 if res == 'FAIL' and p not in KNOWN_FAIL}
        self.assertEqual(fails, {}, 'instrumented program behaves differently')
        fixed = [p for p, res, _, _ in rows if p in KNOWN_FAIL and res != 'FAIL']
        self.assertEqual(fixed, [], 'no longer FAIL: remove from KNOWN_FAIL')


if __name__ == '__main__':
    unittest.main()
