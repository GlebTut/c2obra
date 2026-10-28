"""verifier_stubs.c: every nondet stub reads one whitespace-separated token of test_input.txt.

Signed types: strtoll + cast; unsigned: strtoull + cast ("-1" = all ones); float/double:
strtod plus Prolog's <num>Inf / <num>NaN; a bad token warns and gives 0; EOF gives 0.
__VERIFIER_nondet_memory zero-fills and reads nothing (Sikraken writes no input for it).
Values outside int (seen in Sikraken suites: 4207103166, -2163838572) were cut by the old
fscanf("%d") stubs. Each case runs under -m64, and -m32 where gcc-multilib is installed.

Run from the repo root:  python3 -m unittest unittests.test_verifier_stubs -v
"""
import os, struct, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
sys.path.insert(0, HERE)
from test_c2obra_sh import can_build_m32

PROTOS = r'''#include <stdio.h>
#include <string.h>
#include <stddef.h>
extern int __VERIFIER_nondet_int(void);
extern int __VERIFIER_nondet_bool(void);
extern char __VERIFIER_nondet_char(void);
extern short __VERIFIER_nondet_short(void);
extern long __VERIFIER_nondet_long(void);
extern long long __VERIFIER_nondet_longlong(void);
extern unsigned char __VERIFIER_nondet_uchar(void);
extern unsigned short __VERIFIER_nondet_ushort(void);
extern unsigned int __VERIFIER_nondet_uint(void);
extern unsigned int __VERIFIER_nondet_unsigned(void);
extern unsigned int __VERIFIER_nondet_u32(void);
extern unsigned long __VERIFIER_nondet_ulong(void);
extern unsigned long long __VERIFIER_nondet_ulonglong(void);
extern size_t __VERIFIER_nondet_size_t(void);
extern float __VERIFIER_nondet_float(void);
extern double __VERIFIER_nondet_double(void);
extern void __VERIFIER_nondet_memory(void *, size_t);
int main(void) {
'''

MODELS = [('-m64', 64)] + ([('-m32', 32)] if can_build_m32() else [])


def run_c(body, inputs, flag, write_input=True):
    """Compile PROTOS + body with the stubs; run with inputs. (stdout lines, stderr)."""
    with tempfile.TemporaryDirectory() as d:
        c = os.path.join(d, 't.c')
        with open(c, 'w') as f:
            f.write(PROTOS + body + '\n  return 0;\n}\n')
        exe = os.path.join(d, 't')
        r = subprocess.run(['gcc', '-w', flag, c, os.path.join(SRC, 'verifier_stubs.c'),
                            os.path.join(SRC, 'cov_runtime.c'), '-I', SRC, '-o', exe],
                           capture_output=True, text=True)
        if r.returncode:
            raise AssertionError(r.stderr)
        if write_input:
            with open(os.path.join(d, 'test_input.txt'), 'w') as f:
                f.write('\n'.join(inputs))
        env = dict(os.environ, COVERAGE_OUTPUT=os.path.join(d, 'coverage.json'))
        r = subprocess.run([exe], cwd=d, env=env, capture_output=True, text=True, timeout=30)
        return r.stdout.split('\n')[:-1], r.stderr


def wrap(v, bits, signed):
    v &= (1 << bits) - 1
    return v - (1 << bits) if signed and v >= 1 << (bits - 1) else v


class Stubs(unittest.TestCase):
    def each_model(self, body, inputs, expect):
        """expect(bits) -> expected stdout lines."""
        for flag, bits in MODELS:
            with self.subTest(model=flag):
                out, _ = run_c(body, inputs, flag)
                self.assertEqual(out, expect(bits))

    # one test per new stub
    def test_ulong(self):
        self.each_model('printf("%lu\\n", __VERIFIER_nondet_ulong());', ['4207103166'], lambda b: ['4207103166'])

    def test_ulonglong(self):
        self.each_model('printf("%llu\\n", __VERIFIER_nondet_ulonglong());', ['18446744073709551615'],
                        lambda b: ['18446744073709551615'])

    def test_longlong(self):
        self.each_model('printf("%lld\\n", __VERIFIER_nondet_longlong());', ['-9223372036854775807'],
                        lambda b: ['-9223372036854775807'])

    def test_size_t(self):
        self.each_model('printf("%zu\\n", __VERIFIER_nondet_size_t());', ['4294967295'], lambda b: ['4294967295'])

    def test_u32(self):
        self.each_model('printf("%u\\n", __VERIFIER_nondet_u32());', ['4207103166'], lambda b: ['4207103166'])

    def test_unsigned(self):
        self.each_model('printf("%u\\n", __VERIFIER_nondet_unsigned());', ['-1'], lambda b: ['4294967295'])

    def test_memory_zero_fills_and_reads_no_input(self):
        body = r'''unsigned char buf[16]; memset(buf, 0xAB, sizeof buf);
  __VERIFIER_nondet_memory(buf, sizeof buf);
  __VERIFIER_nondet_memory(buf, 4);
  int all_zero = 1; for (int i = 0; i < 16; i++) all_zero &= buf[i] == 0;
  printf("%d\n%d\n", all_zero, __VERIFIER_nondet_int());'''
        for flag, _ in MODELS:
            with self.subTest(model=flag):
                out, err = run_c(body, ['5'], flag)
                self.assertEqual(out, ['1', '5'])
                self.assertEqual(err.count('c2obra: __VERIFIER_nondet_memory zero-filled, no input read'), 1)

    # values outside int, under -m64 and -m32
    def test_out_of_range(self):
        body = r'''printf("%u\n", __VERIFIER_nondet_uint());
  printf("%ld\n", __VERIFIER_nondet_long());
  printf("%lu\n", __VERIFIER_nondet_ulong());'''
        self.each_model(body, ['4207103166', '-2163838572', '-1'],
                        lambda b: ['4207103166', str(wrap(-2163838572, b, True)), str((1 << b) - 1)])

    def test_int_range_values_unchanged(self):
        body = r'''printf("%d\n", __VERIFIER_nondet_int()); printf("%d\n", __VERIFIER_nondet_char());
  printf("%d\n", __VERIFIER_nondet_uchar()); printf("%d\n", __VERIFIER_nondet_short());
  printf("%d\n", __VERIFIER_nondet_ushort()); printf("%u\n", __VERIFIER_nondet_uint());
  int b1 = __VERIFIER_nondet_bool(); int b2 = __VERIFIER_nondet_bool(); int b3 = __VERIFIER_nondet_bool();
  int b4 = __VERIFIER_nondet_bool();
  printf("%d %d %d %d\n", b1, b2, b3, b4);'''
        self.each_model(body, ['-5', '-3', '255', '-2', '65535', '7', '5', '0', '-1', '0'],
                        lambda b: ['-5', '-3', '255', '-2', '65535', '7', '1 0 1 0'])

    # floats
    def test_prolog_float(self):
        f32 = struct.unpack('f', struct.pack('f', 6.86063887290973e+18))[0]
        body = r'''printf("%.15g\n", __VERIFIER_nondet_double());
  printf("%.9g\n", (double)__VERIFIER_nondet_float());'''
        self.each_model(body, ['6.86063887290973e+18', '6.86063887290973e+18'],
                        lambda b: ['6.86063887290973e+18', '%.9g' % f32])

    def test_inf_nan_then_int(self):
        body = r'''double a = __VERIFIER_nondet_double(); int i = __VERIFIER_nondet_int();
  double n = __VERIFIER_nondet_double(); int j = __VERIFIER_nondet_int();
  float m = __VERIFIER_nondet_float(); double x = __VERIFIER_nondet_double(); double y = __VERIFIER_nondet_double();
  printf("%g %d %d %d %g %g %d\n", a, i, n != n, j, (double)m, x, y != y);'''
        self.each_model(body, ['1.0Inf', '7', '1.5NaN', '8', '-1.0Inf', 'inf', 'nan'],
                        lambda b: ['inf 7 1 8 -inf inf 1'])

    # bad tokens and EOF
    def test_bad_token_warns_and_is_used_up(self):
        for flag, _ in MODELS:
            with self.subTest(model=flag):
                out, err = run_c('int a = __VERIFIER_nondet_int(); int b = __VERIFIER_nondet_int();\n'
                                 '  printf("%d %d\\n", a, b);', ['12abc', '9'], flag)
                self.assertEqual(out, ['0 9'])
                self.assertIn("c2obra: __VERIFIER_nondet_int: input '12abc' is not a number, using 0", err)

    def test_eof_gives_zero_silently(self):
        body = r'''int a = __VERIFIER_nondet_int(); unsigned long u = __VERIFIER_nondet_ulong();
  double d = __VERIFIER_nondet_double();
  printf("%d %lu %g\n", a, u, d);'''
        for flag, _ in MODELS:
            with self.subTest(model=flag):
                out, err = run_c(body, ['3'], flag)
                self.assertEqual(out, ['3 0 0'])
                self.assertEqual(err.count('c2obra:'), 0)

    def test_no_input_file_warns_as_before(self):
        out, err = run_c('printf("%d\\n", __VERIFIER_nondet_int());', [], '-m64', write_input=False)
        self.assertEqual(out, ['0'])
        self.assertIn('[Stubs] Warning: no test_input.txt, using defaults', err)


if __name__ == '__main__':
    unittest.main()
