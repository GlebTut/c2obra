"""c2obra.sh end to end, in a sandbox, with a fake Sikraken.

UnsetEnvGolden: with OUT_DIR, DATA_MODEL, SIKRAKEN_SUITE and LDLIBS unset, c2obra.sh must
produce exactly what it produced before those variables existed. tests/c2obra_sh/golden_unset.json
was recorded with the c2obra.sh of main (commit c56e879) by running this file with --regen;
regenerate it only on purpose, when the default behaviour is meant to change.

Sandbox: a temp dir with a copy of c2obra.sh, symlinks to src/ and venv/, the inputs under in/,
and SIKRAKEN_DIR pointing to a fake Sikraken whose bin/sikraken.sh records its arguments and
writes a fixed two-test suite to sikraken_output/<name>/test-suite (the real layout).

Run from the repo root:  python3 -m unittest tests.test_c2obra_sh -v
Regenerate the golden:   python3 tests/test_c2obra_sh.py --regen
"""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFS = os.path.join(HERE, 'definition')
GOLDEN = os.path.join(HERE, 'c2obra_sh', 'golden_unset.json')
NEW_VARS = ('OUT_DIR', 'DATA_MODEL', 'SIKRAKEN_SUITE', 'LDLIBS')

NONDET_C = r'''#include <stdio.h>
extern int __VERIFIER_nondet_int(void);
int main(void) {
    int x = __VERIFIER_nondet_int();
    if (x > 0) printf("positive\n"); else printf("non-positive\n");
    int i = __VERIFIER_nondet_int();
    if (i % 2 == 0) printf("even\n"); else printf("odd\n");
    return 0;
}
'''

FAKE_SIKRAKEN = r'''#!/usr/bin/env bash
# Fake Sikraken: record the arguments, write the suite where the real one does
# (FAKE_SIK_NOWRITE=1: write nothing, like a run that produced no suite).
echo "$*" >> "$(dirname "$0")/../calls.txt"
[ -n "${FAKE_SIK_NOWRITE:-}" ] && exit 0
f="${@: -1}"; name="$(basename "${f%.*}")"
suite="$(dirname "$0")/../sikraken_output/$name/test-suite"
mkdir -p "$suite"
echo '<testcase><input>4</input><input>2</input></testcase>'  > "$suite/test_input-1.xml"
echo '<testcase><input>-1</input><input>3</input></testcase>' > "$suite/test_input-2.xml"
'''


def make_sandbox(d):
    shutil.copy(os.path.join(ROOT, 'c2obra.sh'), d)
    os.symlink(os.path.join(ROOT, 'src'), os.path.join(d, 'src'))
    os.symlink(os.path.join(ROOT, 'venv'), os.path.join(d, 'venv'))
    os.makedirs(os.path.join(d, 'in'))
    os.makedirs(os.path.join(d, 'sik', 'bin'))
    fake = os.path.join(d, 'sik', 'bin', 'sikraken.sh')
    with open(fake, 'w') as f:
        f.write(FAKE_SIKRAKEN)
    os.chmod(fake, 0o755)


def run_c2obra(d, arg, **env_vars):
    env = {k: v for k, v in os.environ.items() if k not in NEW_VARS + ('CFLAGS', 'VIRTUAL_ENV')}
    env['SIKRAKEN_DIR'] = os.path.join(d, 'sik')
    env.update(env_vars)
    r = subprocess.run(['bash', 'c2obra.sh', arg], cwd=d, env=env, capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def snapshot(d, roots=('output', 'build')):
    """Every file under roots: content for json/csv/.c, existence only for binaries and HTML."""
    files = {}
    for root in roots:
        for dirpath, _, names in os.walk(os.path.join(d, root)):
            for n in names:
                p = os.path.join(dirpath, n)
                rel = os.path.relpath(p, d)
                if n.endswith('.json'):
                    with open(p) as f:
                        data = json.load(f)
                    for key in ('test_runs',):          # run_tests.py runs a suite in threads
                        if isinstance(data, dict) and key in data:
                            data[key] = sorted(data[key], key=lambda t: t['test_case'])
                    if isinstance(data, list):
                        data = sorted(data, key=lambda t: t.get('test_case', ''))
                    files[rel] = data
                elif n.endswith(('.csv', '.c')):
                    with open(p) as f:
                        files[rel] = f.read()
                else:
                    files[rel] = '<exists>'
    calls = os.path.join(d, 'sik', 'calls.txt')
    if os.path.exists(calls):
        with open(calls) as f:
            files['sik/calls.txt'] = f.read()
    return files


def cases():
    """(name, setup(d) -> argument for c2obra.sh)."""
    out = []
    for n in sorted(os.listdir(DEFS)):
        if n.endswith('.c'):
            out.append((n, lambda d, n=n: shutil.copy(os.path.join(DEFS, n), os.path.join(d, 'in')) and f'in/{n}'))

    def nondet(d):
        with open(os.path.join(d, 'in', 'nondet.c'), 'w') as f:
            f.write(NONDET_C)
        return 'in/nondet.c'

    def pairing_error(d):           # X-macro case labels: instrumentation stops (CLAUDE.md)
        shutil.copy(os.path.join(HERE, 'corpusC', 'c07_xmacro_switch.c'), os.path.join(d, 'in'))
        return 'in/c07_xmacro_switch.c'

    def directory(d):
        os.makedirs(os.path.join(d, 'in', 'proj'))
        shutil.copy(os.path.join(DEFS, 'd01_if.c'), os.path.join(d, 'in', 'proj'))
        with open(os.path.join(d, 'in', 'proj', 'nondet.c'), 'w') as f:
            f.write(NONDET_C)
        return 'in/proj'

    out += [('nondet_fake_sikraken', nondet), ('pairing_error', pairing_error), ('directory_mode', directory)]
    return out


def record(name, setup):
    with tempfile.TemporaryDirectory() as d:
        make_sandbox(d)
        code, _ = run_c2obra(d, setup(d))
        snap = snapshot(d)
        snap = {k: v for k, v in snap.items() if not k.endswith('summary_report.html')}
        return {'exit': code, 'files': snap}


class UnsetEnvGolden(unittest.TestCase):
    def test_outputs_match_golden(self):
        with open(GOLDEN) as f:
            golden = json.load(f)
        self.assertEqual(sorted(golden), sorted(n for n, _ in cases()))
        for name, setup in cases():
            with self.subTest(case=name):
                self.assertEqual(record(name, setup), golden[name])


LIBM_C = r'''#include <math.h>
#include <stdio.h>
int main(void) {
    volatile double x = 1000.0;
    double y = log10(x) + cbrt(x);
    if (y > 5.0) printf("big\n"); else printf("small\n");
    return 0;
}
'''


def can_build_m32():
    """gcc -m32 needs gcc-multilib (32-bit libc); CI runners may not have it."""
    with tempfile.TemporaryDirectory() as d:
        c = os.path.join(d, 'm.c')
        with open(c, 'w') as f:
            f.write('#include <stdio.h>\nint main(void) { puts("x"); return 0; }\n')
        return subprocess.run(['gcc', '-m32', c, '-o', os.path.join(d, 'm')],
                              capture_output=True).returncode == 0


def elf_class(path):
    """1 = 32-bit ELF, 2 = 64-bit ELF."""
    with open(path, 'rb') as f:
        return f.read(5)[4]


class NewEnvVars(unittest.TestCase):
    """OUT_DIR, DATA_MODEL, SIKRAKEN_SUITE, LDLIBS (single-file mode)."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        make_sandbox(self.d)
        with open(os.path.join(self.d, 'in', 'nondet.c'), 'w') as f:
            f.write(NONDET_C)
        with open(GOLDEN) as f:
            self.golden = json.load(f)['nondet_fake_sikraken']['files']

    def tearDown(self):
        shutil.rmtree(self.d)

    def calls(self):
        p = os.path.join(self.d, 'sik', 'calls.txt')
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return f.read().split('\n')[:-1]

    def coverage(self, out):
        with open(os.path.join(self.d, out, 'nondet_inst_coverage.json')) as f:
            return json.load(f)['summary']

    def test_out_dir_gets_everything(self):
        code, log = run_c2obra(self.d, 'in/nondet.c', OUT_DIR='res')
        self.assertEqual(code, 0, log)
        self.assertFalse(os.path.exists(os.path.join(self.d, 'output')))
        self.assertFalse(os.path.exists(os.path.join(self.d, 'build')))
        snap = snapshot(self.d, roots=('res',))
        # same content as the default run, under res/ (plus the binary, which was in build/)
        for rel, content in self.golden.items():
            if rel.startswith('output/') and rel.count('/') == 1 and rel != 'output/coverage_report.json':
                self.assertEqual(snap['res/' + rel[len('output/'):]], content, rel)
        self.assertIn('res/output/coverage_report.json', snap)   # run_tests.py's own file
        self.assertIn('res/nondet_test', snap)

    def test_sikraken_suite_given_skips_sikraken(self):
        suite = os.path.join(self.d, 'mysuite')
        os.makedirs(suite)
        with open(os.path.join(suite, 'test_input-1.xml'), 'w') as f:
            f.write('<testcase><input>5</input><input>4</input></testcase>')
        code, log = run_c2obra(self.d, 'in/nondet.c', SIKRAKEN_SUITE=suite, OUT_DIR='res')
        self.assertEqual(code, 0, log)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.coverage('res')['covered_branches'], 2)    # 5 > 0, 4 even

    def test_sikraken_suite_dash_means_no_inputs(self):
        code, log = run_c2obra(self.d, 'in/nondet.c', SIKRAKEN_SUITE='-', OUT_DIR='res')
        self.assertEqual(code, 0, log)
        self.assertEqual(self.calls(), [])
        self.assertIn('No test-suite provided', log)

    def test_data_model(self):
        m32 = can_build_m32()
        for dm, flag, cls in (('ILP32', '-m32', 1), ('LP64', '-m64', 2), ('-m32', '-m32', 1)):
            with self.subTest(dm=dm):
                if flag == '-m32' and not m32:
                    self.skipTest('gcc -m32 cannot link here (install gcc-multilib)')
                out = 'res_' + dm.strip('-')
                code, log = run_c2obra(self.d, 'in/nondet.c', DATA_MODEL=dm, OUT_DIR=out)
                self.assertEqual(code, 0, log)
                self.assertEqual(self.calls()[-1], f'release budget[10] {flag} ../in/nondet.c')
                self.assertEqual(elf_class(os.path.join(self.d, out, 'nondet_test')), cls)
                self.assertEqual(self.coverage(out)['covered_branches'], 4)

    def test_data_model_rejects_unknown(self):
        code, log = run_c2obra(self.d, 'in/nondet.c', DATA_MODEL='LP32')
        self.assertEqual(code, 1)
        self.assertIn('DATA_MODEL must be', log)

    def test_ldlibs(self):
        with open(os.path.join(self.d, 'in', 'm.c'), 'w') as f:
            f.write(LIBM_C)
        code, log = run_c2obra(self.d, 'in/m.c', OUT_DIR='without')
        self.assertNotEqual(code, 0)
        self.assertIn('undefined reference', log)
        code, log = run_c2obra(self.d, 'in/m.c', OUT_DIR='with', LDLIBS='-lm')
        self.assertEqual(code, 0, log)

    def test_suite_lookup_is_exact(self):
        # A stale suite of a longer name must not be used when Sikraken writes none for this file
        stale = os.path.join(self.d, 'sik', 'sikraken_output', 'nondet-1', 'test-suite')
        os.makedirs(stale)
        with open(os.path.join(stale, 'test_input-1.xml'), 'w') as f:
            f.write('<testcase><input>4</input><input>2</input></testcase>')
        code, log = run_c2obra(self.d, 'in/nondet.c', OUT_DIR='res', FAKE_SIK_NOWRITE='1')
        self.assertEqual(code, 0, log)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn('No Sikraken test suite found', log)
        self.assertNotIn('nondet-1', log)


if __name__ == '__main__':
    if '--regen' in sys.argv:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, 'w') as f:
            json.dump({n: record(n, s) for n, s in cases()}, f, indent=1, sort_keys=True)
        print(f'wrote {GOLDEN}')
    else:
        unittest.main()
