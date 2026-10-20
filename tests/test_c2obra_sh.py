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
# Fake Sikraken: record the arguments, write the suite where the real one does.
echo "$*" >> "$(dirname "$0")/../calls.txt"
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


if __name__ == '__main__':
    if '--regen' in sys.argv:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, 'w') as f:
            json.dump({n: record(n, s) for n, s in cases()}, f, indent=1, sort_keys=True)
        print(f'wrote {GOLDEN}')
    else:
        unittest.main()
