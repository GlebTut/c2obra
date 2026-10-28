"""instrument.strip_verifier_boilerplate(): a program's own reach_error()/__VERIFIER_error()
definition is removed so verifier_stubs.c's version (dump coverage, exit 1) is linked.

Pilot 2026-10-20: recursified_nested_1b.c writes 'void reach_error()' and the '{' on the next
line; the definition was kept and the link failed with 'multiple definition of reach_error'.

Run from the repo root:  python3 -m unittest unittests.test_verifier_boilerplate -v
"""
import contextlib, io, json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'src')
sys.path.insert(0, SRC)
import instrument as I

NESTED_1B_STYLE = '''extern void abort(void);
extern void __assert_fail(const char *, const char *, unsigned int, const char *) __attribute__((__nothrow__, __leaf__)) __attribute__((__noreturn__));
void reach_error()
{
  __assert_fail("0", "nested_1b.c", 13, "reach_error");
}
extern int __VERIFIER_nondet_int(void);
int main()
{
  int x = __VERIFIER_nondet_int();
  if (x > 5)
  {
    reach_error();
  }
  return 0;
}
'''


def strip(code):
    return I.strip_verifier_boilerplate(code)


class RemoveDefinition(unittest.TestCase):
    def test_brace_on_same_line(self):
        self.assertEqual(strip('int a;\nvoid reach_error() { abort(); }\nint b;'), 'int a;\nint b;')

    def test_brace_on_next_line(self):
        code = 'int a;\nvoid reach_error()\n{\n  abort();\n}\nint b;'
        self.assertEqual(strip(code), 'int a;\nint b;')

    def test_brace_after_attribute_and_comment_lines(self):
        code = 'int a;\nvoid __VERIFIER_error(void)\n  /* never returns */\n{ abort(); }\nint b;'
        self.assertEqual(strip(code), 'int a;\nint b;')

    def test_declarations_are_kept(self):
        for code in ('void reach_error(void);\nint b;', 'void reach_error(void)\n;\nint b;',
                     'extern void reach_error();\nint b;'):
            with self.subTest(code=code):
                self.assertEqual(strip(code), code)

    def test_calls_are_kept(self):
        code = 'int main(void)\n{\n  reach_error();\n  return 0;\n}'
        self.assertEqual(strip(code), code)

    def test_no_brace_within_limit_keeps_lines(self):
        # header + 5 lines without '{' or ';': not treated as a definition, nothing removed
        code = 'void reach_error()\na\nb\nc\nd\ne\nf\n{ }\nint b;'
        self.assertEqual(strip(code), code)


class NestedOneB(unittest.TestCase):
    def test_links_and_uses_the_stub(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'nested_1b.c')
            with open(src, 'w') as f:
                f.write(NESTED_1B_STYLE)
            inst = os.path.join(d, 'nested_1b_inst.c')
            with contextlib.redirect_stdout(io.StringIO()):
                I.instrument_file(src, inst, flags=[])
            with open(inst) as f:
                self.assertNotIn('__assert_fail("0"', f.read())
            exe = os.path.join(d, 'a.out')
            r = subprocess.run(['gcc', '-w', inst, os.path.join(SRC, 'cov_runtime.c'),
                                os.path.join(SRC, 'verifier_stubs.c'), '-I', SRC, '-o', exe],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(d, 'test_input.txt'), 'w') as f:
                f.write('9\n')
            env = dict(os.environ, COVERAGE_OUTPUT=os.path.join(d, 'coverage.json'))
            r = subprocess.run([exe], cwd=d, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 1)               # verifier_stubs.c reach_error: exit(1)
            with open(os.path.join(d, 'coverage.json')) as f:
                self.assertEqual(json.load(f)['branches'], [{'id': 1, 'true': 1, 'false': 0}])


if __name__ == '__main__':
    unittest.main()
