"""Behaviour preservation (spec 5.5): original and instrumented program, same stdout and exit status.

Corpus: tests/corpusC/c*.c, tests/examples/*.c, tests/loop-simple/*.c, tests/loop-lit/*.c,
tests/definition/d*.c. Each program is instrumented (flags=[] as in the other tests), the
original and the instrumented copy are compiled with gcc (test_definition.build_and_run) and
both are run with no input (stdin /dev/null) and a short timeout.

Every program gets one row: PASS (same behaviour), FAIL (different, or the instrumented copy
does not compile) or SKIP with a reason (nondeterministic input, original does not compile,
original times out, or instrument.py stops with an error). Only FAIL fails the test.

The table is printed. With C2OBRA_BEHAVIOUR_MD=1 it is also written to
tests/behaviour_check_results.md:
    C2OBRA_BEHAVIOUR_MD=1 venv/bin/python3 -m unittest tests.test_behaviour -v

Run from the repo root:  python3 -m unittest tests.test_behaviour -v
"""
import contextlib, datetime, glob, importlib.metadata, io, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)
import instrument as I
from test_definition import build_and_run

CORPUS = ['corpusC/c*.c', 'examples/*.c', 'loop-simple/*.c', 'loop-lit/*.c', 'definition/d*.c']
TIMEOUT = 5                      # seconds per run
RESULTS_MD = os.path.join(HERE, 'behaviour_check_results.md')


def corpus():
    return [p for g in CORPUS for p in sorted(glob.glob(os.path.join(HERE, g)))]


def first_line(text):
    return next((l.strip() for l in text.splitlines() if l.strip()), '')


def gcc_error(text):
    """The first compiler/linker error line of gcc's output, without the file path."""
    line = next((l for l in text.splitlines() if 'error' in l or 'undefined reference' in l), first_line(text))
    return line.strip().rsplit(': ', 2)[-1] if 'undefined reference' in line else line.strip()


def check_program(path):
    """(result, reason, detail) for one program; detail holds both runs on FAIL."""
    with open(path, errors='replace') as f:
        if '__VERIFIER_nondet' in f.read():
            return 'SKIP', 'nondeterministic input (__VERIFIER_nondet_*)', None
    name = os.path.basename(path)
    inc = ['-I', os.path.dirname(path)]            # local headers (c10_include_header.c)
    with tempfile.TemporaryDirectory() as d:
        orig = os.path.join(d, name)
        shutil.copy(path, orig)
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
                I.instrument_file(orig, inst, flags=[])
        except SystemExit:
            err = next((l for l in out.getvalue().splitlines() if l.startswith('❌')), 'exit')
            return 'SKIP', f'instrument.py stopped: {err[:120]}', None
        try:
            got = build_and_run(d, inst, inc + [os.path.join(SRC, 'cov_runtime.c'),
                                                os.path.join(SRC, 'verifier_stubs.c')], timeout=TIMEOUT)
        except AssertionError as e:
            return 'FAIL', 'instrumented copy does not compile', {'error': str(e)}
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


def write_md(rows, counts, versions):
    with open(RESULTS_MD, 'w') as f:
        f.write('# Behaviour preservation on the corpus\n\n')
        f.write(f'Date: {datetime.date.today().isoformat()}. Written by `tests/test_behaviour.py` '
                f'(`C2OBRA_BEHAVIOUR_MD=1`).\n\n')
        f.write('Original and instrumented program compiled with gcc, run with no input (stdin '
                f'`/dev/null`) and a {TIMEOUT} s timeout; stdout and exit status compared.\n\n')
        f.write('Tools:\n\n' + ''.join(f'- {k}: `{v}`\n' for k, v in versions.items()) + '\n')
        f.write(f"PASS {counts['PASS']}, FAIL {counts['FAIL']}, SKIP {counts['SKIP']} "
                f"(of {len(rows)} programs)\n\n")
        f.write(table(rows) + '\n')


class BehaviourPreserved(unittest.TestCase):
    def test_corpus(self):
        paths = corpus()
        self.assertTrue(paths)
        rows = []
        for p in paths:
            res, reason, detail = check_program(p)
            rows.append((os.path.relpath(p, HERE), res, reason, detail))
        counts = {k: sum(1 for r in rows if r[1] == k) for k in ('PASS', 'FAIL', 'SKIP')}
        print('\n' + table(rows))
        print(f"PASS {counts['PASS']}, FAIL {counts['FAIL']}, SKIP {counts['SKIP']}")
        if os.environ.get('C2OBRA_BEHAVIOUR_MD') == '1':
            write_md(rows, counts, tool_versions())

        self.assertEqual(len(rows), len(paths))                     # no program dropped
        for p, res, reason, _ in rows:
            self.assertIn(res, ('PASS', 'FAIL', 'SKIP'))
            if res == 'SKIP':
                self.assertTrue(reason, f'{p}: SKIP without a reason')
        fails = {p: (reason, detail) for p, res, reason, detail in rows if res == 'FAIL'}
        self.assertEqual(fails, {}, 'instrumented program behaves differently')


if __name__ == '__main__':
    unittest.main()
