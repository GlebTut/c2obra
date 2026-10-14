"""Regression test: cover() IDs in the instrumented source must equal the IDs in branch_map.json.

Before the fix, instrument_code() skipped constructs it could not wrap (for(;;), a switch with
no case labels) without consuming an ID, while write_branch_map() still assigned one, so every
later map entry pointed at the wrong construct.

Run from the repo root:  python3 -m unittest discover -s tests -p "test_*.py" -v
"""
import json, os, re, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import instrument as I


def cover_ids(code):
    """IDs of every cover(<cond>, <id>) call; paren-balanced so nested calls cannot confuse it."""
    out = []
    for m in re.finditer(r'\bcover\(', code):
        i, depth = m.end(), 1
        last = i
        while i < len(code) and depth:
            ch = code[i]
            if ch in '([{': depth += 1
            elif ch in ')]}': depth -= 1
            elif ch == ',' and depth == 1: last = i + 1
            i += 1
        out.append(int(code[last:i - 1]))
    return sorted(set(out))


def ids_for(c_source):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 't.c')
        with open(path, 'w') as f:
            f.write(c_source)
        tree, src = I.parse_c_file(path)
        branches = I.find_branches(tree)
        code = I.instrument_code(src, branches)
        I.write_branch_map(branches, src, os.path.join(d, 'm.json'), path)
        mapped = [b['id'] for b in json.load(open(os.path.join(d, 'm.json')))['branches']]
    emitted = cover_ids(code)
    return emitted, mapped


class IdSync(unittest.TestCase):
    def check(self, body):
        emitted, mapped = ids_for("int f(int a,int b);int g(int a,int b);\nint main(void){int i=0,n=3;\n" + body + "\nreturn i;}\n")
        self.assertEqual(emitted, mapped)
        self.assertEqual(mapped, list(range(1, len(mapped) + 1)))   # contiguous from 1
        return mapped

    def test_infinite_for_before_other_branches(self):
        self.assertEqual(len(self.check("for(;;){break;}\nif(i>0){i=1;}\nwhile(i<n){i++;}")), 2)

    def test_empty_switch_before_other_branches(self):
        self.assertEqual(len(self.check("switch(i){}\nif(i>0){i=1;}")), 1)

    def test_all_branch_kinds(self):
        self.check("if(i){i=1;}\nwhile(i<n){i++;}\ndo{i++;}while(i<n);\nfor(;i<n;){i++;}\n"
                   "switch(i){case 1: break; case 2: break;}\nn = i ? 1 : 2;")

    def test_nested_call_in_condition(self):
        self.check("n = f(i, 1) ? 1 : 2;\nif (g(i, 2) > 0) { i = 1; }")

    def test_no_branches(self):
        self.assertEqual(self.check("i=1;"), [])

    def test_switch_without_condition_node(self):
        # instrument_code() cannot wrap a switch whose condition node is missing; is_instrumentable()
        # must reject it too, or write_branch_map() gives it IDs and every later ID shifts.
        # Tree-sitter always gives switch (x) a parenthesized_expression, so the node is hand-built.
        class NoCondition:
            def __init__(self, node):
                self._node = node
                self.children = [c for c in node.children if c.type != 'parenthesized_expression']

            def __getattr__(self, name):
                return getattr(self._node, name)

        src_text = ("int main(void){int i=0;\nif(i>0){i=1;}\nswitch(i){case 1: break; default: break;}\n"
                    "while(i<3){i++;}\nreturn i;}\n")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 't.c')
            with open(path, 'w') as f:
                f.write(src_text)
            tree, src = I.parse_c_file(path)
            branches = I.find_branches(tree)
            for b in branches:
                if b['type'] == 'switch_statement':
                    b['node'] = NoCondition(b['node'])
            self.assertTrue(any(isinstance(b['node'], NoCondition) for b in branches))
            code = I.instrument_code(src, branches)
            I.write_branch_map(branches, src, os.path.join(d, 'm.json'), path)
            with open(os.path.join(d, 'm.json')) as f:
                mapped = [b['id'] for b in json.load(f)['branches']]
        self.assertEqual(cover_ids(code), mapped)
        self.assertEqual(mapped, [1, 2])        # the if and the while; the switch gets no ID


if __name__ == '__main__':
    unittest.main()
