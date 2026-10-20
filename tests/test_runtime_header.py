"""cov_runtime.h has no system headers, so it cannot clash with a program's own types.

Pilot 2026-10-20: 6 of 10 .i tasks failed to compile with 'conflicting types for __fsid_t'
(glibc's typedef struct { int __val[2]; } __fsid_t, already in the .i, defined again through
the header's <stdint.h>) or 'conflicting types for uint64_t' (Intel-TDX: unsigned long long).

Run from the repo root:  python3 -m unittest tests.test_runtime_header -v
"""
import contextlib, io, json, os, re, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)
import instrument as I
import edges as E
from test_c2obra_sh import can_build_m32

OWN_TYPES = r'''typedef struct { int __val[2]; } __fsid_t;
typedef unsigned long long int uint64_t;
typedef unsigned int uint32_t;
extern int __VERIFIER_nondet_int(void);
int main(void) {
    uint64_t big = (uint64_t)__VERIFIER_nondet_int();
    __fsid_t id; id.__val[0] = 2;
    if (big > 3) return id.__val[0];
    return 0;
}
'''

GLIBC_TYPES = r'''#include <sys/types.h>
#include <stdint.h>
extern int __VERIFIER_nondet_int(void);
int main(void) {
    uint64_t big = (uint64_t)__VERIFIER_nondet_int();
    __fsid_t id; id.__val[0] = 2;
    if (big > 3) return id.__val[0];
    return 0;
}
'''


def instrument(d, name, text):
    src = os.path.join(d, name)
    with open(src, 'w') as f:
        f.write(text)
    inst = os.path.join(d, os.path.splitext(name)[0] + '_inst.c')
    with contextlib.redirect_stdout(io.StringIO()):
        I.instrument_file(src, inst, flags=[])
    with open(inst[:-2] + '_branch_map.json') as f:
        return inst, json.load(f)


def build(d, inst, extra=()):
    exe = inst[:-2]
    r = subprocess.run(['gcc', '-w', *extra, inst, os.path.join(SRC, 'cov_runtime.c'),
                        os.path.join(SRC, 'verifier_stubs.c'), '-I', SRC, '-o', exe],
                       capture_output=True, text=True)
    return r, exe


def run(d, exe, inputs):
    with open(os.path.join(d, 'test_input.txt'), 'w') as f:
        f.write('\n'.join(inputs))
    env = dict(os.environ, COVERAGE_OUTPUT=os.path.join(d, 'coverage.json'))
    r = subprocess.run([exe], cwd=d, env=env, capture_output=True, text=True, timeout=30)
    with open(os.path.join(d, 'coverage.json')) as f:
        return r, {b['id']: b for b in json.load(f)['branches']}


class RuntimeHeader(unittest.TestCase):
    def test_header_includes_nothing(self):
        with open(os.path.join(SRC, 'cov_runtime.h')) as f:
            self.assertEqual(re.findall(r'^\s*#\s*include\b.*', f.read(), re.M), [])

    def test_program_with_own_fsid_t_and_uint64_t(self):
        models = [('-m64', 'LP64')] + ([('-m32', 'ILP32')] if can_build_m32() else [])
        for flag, name in models:
            with self.subTest(model=name), tempfile.TemporaryDirectory() as d:
                inst, branch_map = instrument(d, 'own.c', OWN_TYPES)
                r, exe = build(d, inst, [flag])
                self.assertEqual(r.returncode, 0, r.stderr)
                r, cov = run(d, exe, ['5'])
                self.assertEqual(r.returncode, 2)
                self.assertEqual(E.edge_coverage(branch_map, cov), (1, 2))

    def test_program_with_own_size_t(self):
        """Pilot2 2026-10-20: 5 tasks failed with "unknown type name 'size_t'". The program's own
        typedef unsigned int size_t; was deleted by strip_verifier_boilerplate(), a pattern added
        (310d799) when cov_runtime.h still included <stdio.h>, whose LP64 size_t conflicted."""
        own_size_t = ('typedef unsigned int size_t;\n'
                      'extern void *malloc(size_t);\n'
                      'extern int __VERIFIER_nondet_int(void);\n'
                      'int main(void) {\n'
                      '    void *p = malloc((size_t)__VERIFIER_nondet_int());\n'
                      '    if (p) return 0;\n'
                      '    return 1;\n'
                      '}\n')
        models = [('-m64', 'LP64')] + ([('-m32', 'ILP32')] if can_build_m32() else [])
        for flag, name in models:
            with self.subTest(model=name), tempfile.TemporaryDirectory() as d:
                inst, branch_map = instrument(d, 'own_size_t.c', own_size_t)
                with open(inst) as f:
                    self.assertIn('typedef unsigned int size_t;', f.read())
                r, exe = build(d, inst, [flag])
                self.assertEqual(r.returncode, 0, r.stderr)
                r, cov = run(d, exe, ['16'])
                self.assertEqual((r.returncode, E.edge_coverage(branch_map, cov)), (0, (1, 2)))

    def test_preprocessed_glibc_types(self):
        """gcc -E of a program using <sys/types.h>: the .i holds glibc's __fsid_t and uint64_t."""
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, 'g.c')
            with open(c, 'w') as f:
                f.write(GLIBC_TYPES)
            i = subprocess.run(['gcc', '-E', '-P', c], capture_output=True, text=True, check=True).stdout
            self.assertIn('__fsid_t;', i)
            inst, branch_map = instrument(d, 'g.i', i)
            r, exe = build(d, inst)
            self.assertEqual(r.returncode, 0, r.stderr)
            r, cov = run(d, exe, ['1'])
            self.assertEqual((r.returncode, E.edge_coverage(branch_map, cov)), (0, (1, 2)))

    def test_out_of_bounds_id_reported(self):
        """Ids beyond MAX_BRANCHES go through __c2obra_cover_out_of_bounds() (stderr, value 0);
        as before, the condition is then not evaluated. MAX_BRANCHES=2 holds id 1 only.
        (MAX_BRANCHES must be even: dump_coverage() reads counters in pairs. c2obra.sh
        always passes ids * 2.)"""
        two = OWN_TYPES.replace('    if (big > 3) return id.__val[0];',
                                '    if (big > 3) return id.__val[0];\n    if (big > 1) return 7;')
        with tempfile.TemporaryDirectory() as d:
            inst, _ = instrument(d, 'two.c', two)
            r, exe = build(d, inst, ['-DMAX_BRANCHES=2'])
            self.assertEqual(r.returncode, 0, r.stderr)
            r, cov = run(d, exe, ['2'])                 # 2 > 3 false; id 2 out of bounds -> 0
            self.assertIn('cover(): branch_id 2 out of bounds', r.stderr)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(cov, {1: {'id': 1, 'true': 0, 'false': 1}})


if __name__ == '__main__':
    unittest.main()
