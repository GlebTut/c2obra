#!/usr/bin/env python3
"""
C²oBra - Source Instrumenter
Iteration 1: Basic branch instrumentation ->
Iteration 2: Switch instrumentation + error handling + multi-file directory support ->
Iteration 3: Explicit else branch metadata tracking
"""


import sys, json, os, re
from tree_sitter import Language, Parser
import tree_sitter_c


# Verifier boilerplate that conflicts with verifier_stubs.c at link time
# These are stripped from instrumented output
VERIFIER_STUB_PATTERNS = [
    r'void\s+reach_error\s*\([^)]*\)\s*\{[\s\S]*?\}',
    r'void\s+__VERIFIER_error\s*\([^)]*\)\s*\{[\s\S]*?\}',
    r'extern\s+void\s+__assert_fail\s*\([^;]*\)\s*;',
    r'typedef\s+unsigned\s+int\s+size_t\s*;',
]


def parse_c_file(filename):
    """Parse C source file with tree-sitter"""
    try:
        with open(filename, 'rb') as f:
            source_code = f.read()
    except OSError as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)

    C_LANGUAGE = Language(tree_sitter_c.language(), "c")
    parser = Parser()
    parser.set_language(C_LANGUAGE)
    tree = parser.parse(source_code)
    return tree, source_code


def find_branches(tree):
    """Find all branch points in the AST"""
    branches = []

    def walk_tree(node):
        if node.type in [
            'if_statement', 'for_statement', 'while_statement',
            'switch_statement', 'do_statement', 'conditional_expression'
        ]:
            branches.append({
                'type':        node.type,
                'node':        node,
                'start_byte':  node.start_byte,
                'end_byte':    node.end_byte,
                'start_point': node.start_point,
                'end_point':   node.end_point,
            })
        for child in node.children:
            walk_tree(child)

    walk_tree(tree.root_node)
    return branches


def get_condition_node(branch_node):
    """Extract the condition node from an if/for/while statement"""
    for child in branch_node.children:
        if child.type == 'parenthesized_expression':
            return child
    return None


def get_for_condition_node(for_node):
    """Extract the condition from a for loop"""
    cond = for_node.child_by_field_name("condition")
    if cond is not None:
        return cond
    for child in for_node.children:
        if child.type in (
            "binary_expression", "identifier", "call_expression",
            "parenthesized_expression", "relational_expression",
            "logical_expression", "update_expression", "assignment_expression",
        ):
            return child
    return None


def get_switch_cases(switch_node, source_code):
    """Extract switch expression and all case/default labels"""
    expr = ""
    for child in switch_node.children:
        if child.type == 'parenthesized_expression':
            inner = source_code[child.start_byte:child.end_byte].decode('utf-8')
            expr = inner[1:-1].strip()
            break

    cases = []
    for child in switch_node.children:
        if child.type == 'compound_statement':
            for stmt in child.children:
                if stmt.type == 'case_statement':
                    first = stmt.children[0] if stmt.children else None
                    if first and first.type == 'default':
                        cases.append({'kind': 'default', 'line': stmt.start_point[0] + 1})
                        continue
                    value_node = None
                    for sub in stmt.children:
                        if sub.type == ':':
                            break
                        if sub.type not in ('case', 'comment'):
                            value_node = sub
                    if value_node is None:
                        continue
                    val = source_code[value_node.start_byte:value_node.end_byte].decode('utf-8').strip()
                    cases.append({'kind': 'case', 'value': val, 'line': stmt.start_point[0] + 1})
    return {'expression': expr, 'cases': cases}


def get_else_info(if_node):
    """
    Inspect an if_statement node for an else clause.
    Returns (has_else, else_line, is_else_if) where:
      - has_else    : bool — True if an explicit else clause exists
      - else_line   : int  — source line of the else keyword
      - is_else_if  : bool — True if the else body is another if_statement (else if chain)
    """
    for child in if_node.children:
        if child.type == 'else_clause':
            else_line = child.start_point[0] + 1
            # Check if the body of the else is itself an if_statement
            is_else_if = any(c.type == 'if_statement' for c in child.children)
            return True, else_line, is_else_if
    return False, None, False


def build_cover_chain(switch_meta, base_id):
    """Build the if/else if cover() chain to inject before switch"""
    expr   = switch_meta['expression']
    cases  = switch_meta['cases']
    lines  = []
    current_id = base_id

    for i, case in enumerate(cases):
        prefix = "if " if i == 0 else "else if "
        if case['kind'] == 'case':
            condition = f"{expr} == {case['value']}"
            line = f"{prefix}(cover({condition}, {current_id})) ;"
        else:
            line = f"else cover(1, {current_id});"
        lines.append(line)
        current_id += 1

    has_default = any(c['kind'] == 'default' for c in cases)
    if not has_default:
        lines.append(f"else cover(0, {current_id});")

    result = lines[0]
    for l in lines[1:]:
        result += "\n" + l
    return result + "\n"


class SourceRewriter:
    """Collects source edits and applies them safely end-to-start"""

    def __init__(self, source: bytes):
        self.source = source
        self.edits  = []

    def replace(self, start, end, text):
        self.edits.append((start, end, text))

    def apply(self):
        result = self.source
        for start, end, text in sorted(self.edits, key=lambda e: e[0], reverse=True):
            result = result[:start] + text.encode() + result[end:]
        return result.decode('utf-8')


def strip_verifier_boilerplate(code: str) -> str:
    """
    Remove reach_error() / __VERIFIER_error() definitions and __assert_fail
    declarations that conflict with verifier_stubs.c at link time.
    """
    for pattern in VERIFIER_STUB_PATTERNS:
        code = re.sub(pattern, '/* removed: defined in verifier_stubs.c */', code, flags=re.DOTALL)
    return code


def instrument_code(source_code, branches, start_id=1):
    """Wrap branch conditions with cover() macro. start_id enables global IDs across files."""
    rewriter   = SourceRewriter(source_code)
    current_id = start_id

    for branch in sorted(branches, key=lambda b: b['start_byte']):
        branch_type = branch['type']
        node        = branch['node']

        if branch_type in ['if_statement', 'while_statement', 'do_statement']:
            condition_node = get_condition_node(node)
            if condition_node:
                cond_start     = condition_node.start_byte
                cond_end       = condition_node.end_byte
                condition_text = source_code[cond_start:cond_end].decode('utf-8')
                inner = condition_text[1:-1] if condition_text.startswith('(') and condition_text.endswith(')') else condition_text
                rewriter.replace(cond_start, cond_end, f"(cover({inner}, {current_id}))")
                current_id += 1

        elif branch_type == 'for_statement':
            condition_node = get_for_condition_node(node)
            if condition_node:
                cond_start     = condition_node.start_byte
                cond_end       = condition_node.end_byte
                condition_text = source_code[cond_start:cond_end].decode('utf-8').strip()
                if condition_text:
                    rewriter.replace(cond_start, cond_end, f" cover({condition_text}, {current_id}) ")
                    current_id += 1

        elif branch_type == 'switch_statement':
            switch_meta = get_switch_cases(node, source_code)
            if not switch_meta['cases']:
                continue
            cover_chain = build_cover_chain(switch_meta, current_id)
            rewriter.replace(node.start_byte, node.start_byte, cover_chain)
            has_default = any(c['kind'] == 'default' for c in switch_meta['cases'])
            current_id += len(switch_meta['cases']) + (0 if has_default else 1)

        elif branch_type == 'conditional_expression':
            # ternary: condition ? true_expr : false_expr
            # condition is the first child node before '?'
            condition_node = node.children[0] if node.children else None
            if condition_node:
                cond_start     = condition_node.start_byte
                cond_end       = condition_node.end_byte
                condition_text = source_code[cond_start:cond_end].decode('utf-8').strip()
                if condition_text:
                    rewriter.replace(cond_start, cond_end, f"cover({condition_text}, {current_id})")
                    current_id += 1

    code = rewriter.apply()
    code = strip_verifier_boilerplate(code)
    VERIFIER_PREAMBLE = '''\
#include "cov_runtime.h"
/* verifier stub forward declarations */
extern void reach_error(void);
extern void __VERIFIER_error(void);
extern void __VERIFIER_assume(int);

'''
    return VERIFIER_PREAMBLE + code


def write_branch_map(branches, source_code, output_file, input_file, start_id=1):
    """Write branch metadata to branch_map.json. Returns next available branch ID."""
    sorted_branches = sorted(branches, key=lambda b: b['start_byte'])
    branch_map  = []
    current_id  = start_id

    for branch in sorted_branches:
        branch_type = branch['type']
        node        = branch['node']

        if branch_type == 'switch_statement':
            meta = get_switch_cases(node, source_code)
            for case in meta['cases']:
                label = f"case {case['value']}" if case['kind'] == 'case' else 'default'
                branch_map.append({
                    "id":    current_id,
                    "line":  case['line'],
                    "type":  "switch_case",
                    "label": label,
                })
                current_id += 1
            if not any(c['kind'] == 'default' for c in meta['cases']):
                branch_map.append({
                    "id":    current_id,
                    "line":  branch['start_point'][0] + 1,
                    "type":  "switch_implicit_default",
                    "label": "implicit default",
                })
                current_id += 1

        elif branch_type == 'if_statement':
            has_else, else_line, is_else_if = get_else_info(node)

            # Build a human-readable label for the true edge
            if has_else and is_else_if:
                true_label  = "if (true)"
                false_label = "else if →"
            elif has_else:
                true_label  = "if (true)"
                false_label = f"else @ line {else_line}"
            else:
                true_label  = "if (true)"
                false_label = "no else (false)"

            branch_map.append({
                "id":         current_id,
                "line":       branch['start_point'][0] + 1,
                "type":       branch_type,
                "true_label": true_label,
                "false_label": false_label,
            })
            current_id += 1

        elif branch_type == 'conditional_expression':
            branch_map.append({
                "id":          current_id,
                "line":        branch['start_point'][0] + 1,
                "type":        "ternary_expression",
                "true_label":  "ternary (true)",
                "false_label": "ternary (false)",
            })
            current_id += 1

        else:
            # for_statement, while_statement, do_statement
            branch_map.append({
                "id":   current_id,
                "line": branch['start_point'][0] + 1,
                "type": branch_type,
            })
            current_id += 1

    with open(output_file, 'w') as f:
        json.dump({
            "source_file": os.path.relpath(input_file),
            "branches":    branch_map,
        }, f, indent=2)
    print(f"✓ Wrote branch map to {output_file}")
    return current_id


def instrument_file(input_file, output_file, start_id=1):
    """
    Instrument a single .c file. Returns next available branch ID.
    start_id allows global branch IDs across multiple files.
    """
    print(f"Instrumenting {input_file}...")

    if not os.path.exists(input_file):
        print(f"❌ Error: File '{input_file}' not found")
        sys.exit(1)
    if not input_file.endswith('.c'):
        print(f"❌ Error: Expected a .c file, got '{input_file}'")
        sys.exit(1)
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        print(f"❌ Error: Output directory '{output_dir}' does not exist")
        sys.exit(1)

    tree, source_code = parse_c_file(input_file)
    if tree.root_node.has_error:
        print("⚠️ Warning: Source file contains syntax errors — instrumentation may be incomplete")

    branches = find_branches(tree)
    if not branches:
        print("⚠️ Warning: No branches found — output will be identical to input")
    else:
        total_branch_edges = len(branches) * 2
        print(f"✓ Found {total_branch_edges} branches ({len(branches)} branch constructs):")
        for i, branch in enumerate(branches, 1):
            line = branch['start_point'][0] + 1
            btype = branch['type'].replace('_statement', '').replace('_', '-')
            print(f"  {i}. {btype} at line {line}  →  true branch + false branch")

    instrumented_code = instrument_code(source_code, branches, start_id=start_id)

    try:
        with open(output_file, 'w') as f:
            f.write(instrumented_code)
        print(f"✓ Wrote {output_file}")
    except OSError as e:
        print(f"❌ Error writing output: {e}")
        sys.exit(1)

    map_file   = output_file.replace('.c', '_branch_map.json')
    next_id    = write_branch_map(branches, source_code, map_file, input_file, start_id=start_id)
    total_counters = (next_id - start_id) * 2
    print(f"BRANCH_COUNTERS={total_counters}")
    print(f"Done! Successfully instrumented {len(branches) * 2} branches.\n")
    return next_id


def instrument_directory(input_dir, output_dir):
    """
    Recursively instrument all .c files in input_dir, writing results to output_dir.
    Branch IDs are globally unique across all files.
    """
    c_files = []
    for root, _, files in os.walk(input_dir):
        for fname in sorted(files):
            if fname.endswith('.c'):
                c_files.append(os.path.join(root, fname))

    if not c_files:
        print(f"⚠️ No .c files found in '{input_dir}'")
        return

    print(f"Found {len(c_files)} .c file(s) in '{input_dir}'")

    next_id = 1
    for input_file in c_files:
        rel_path    = os.path.relpath(input_file, input_dir)
        base_name   = os.path.splitext(rel_path)[0] + '_inst.c'
        output_file = os.path.join(output_dir, base_name)
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        next_id = instrument_file(input_file, output_file, start_id=next_id)

    total_branches = next_id - 1
    print(f"✅ Directory instrumentation complete.")
    print(f"   Files instrumented      : {len(c_files)}")
    total_branch_edges = total_branches * 2
    print(f"   Total branch constructs : {total_branches}")
    print(f"   Total branches          : {total_branch_edges}")
    print(f"BRANCH_COUNTERS={total_branch_edges}")


def main():
    if len(sys.argv) == 3:
        input_path  = sys.argv[1]
        output_path = sys.argv[2]

        if os.path.isdir(input_path):
            if not os.path.exists(output_path):
                os.makedirs(output_path, exist_ok=True)
            instrument_directory(input_path, output_path)
        else:
            instrument_file(input_path, output_path, start_id=1)
    else:
        print("Usage:")
        print("  Single file : python3 instrument.py <source.c> <output.c>")
        print("  Directory   : python3 instrument.py <source_dir/> <output_dir/>")
        sys.exit(1)


if __name__ == "__main__":
    main()
