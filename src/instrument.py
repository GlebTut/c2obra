#!/usr/bin/env python3
"""
C²oBra - Source Instrumenter
Iteration 1: Basic branch instrumentation ->
Iteration 2: Switch instrumentation + error handling + multi-file directory support ->
Iteration 3: Explicit else branch metadata tracking
Phase 2: Clang decides which decisions exist (clang_scan.py); Tree-sitter finds the text to wrap
"""


import sys, json, os, re
from collections import Counter
from tree_sitter import Language, Parser
import tree_sitter_c
import clang_scan


# Verifier boilerplate that conflicts with verifier_stubs.c at link time
# These are stripped from instrumented output
# Flags used when the caller gives none (no "--" on the command line). SV-COMP files use
# LARGE_INT without defining it; the pipeline's gcc gets it from cov_runtime.h (same value).
DEFAULT_SVCOMP_FLAGS = ['-DLARGE_INT=1000000']

# Tree-sitter node type -> Clang decision kind (clang_scan.KINDS)
TS_KIND = {'if_statement': 'if', 'for_statement': 'for', 'while_statement': 'while',
           'do_statement': 'do', 'switch_statement': 'switch', 'conditional_expression': '?:'}


class PairingError(Exception):
    """A Clang decision has no Tree-sitter node to wrap, or the node cannot be wrapped."""


VERIFIER_STUB_PATTERNS = [
    r'void\s+reach_error\s*\([^)]*\)\s*\{[^}]*\}',
    r'void\s+__VERIFIER_error\s*\([^)]*\)\s*\{[^}]*\}',
    r'extern\s+[^;]*__assert_fail[^;]*;',
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
    """Find all branch points in the AST — iterative to avoid recursion overhead"""
    BRANCH_TYPES = frozenset([
        'if_statement', 'for_statement', 'while_statement',
        'switch_statement', 'do_statement', 'conditional_expression'
    ])
    branches = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in BRANCH_TYPES:
            branches.append({
                'type':        node.type,
                'node':        node,
                'start_byte':  node.start_byte,
                'end_byte':    node.end_byte,
                'start_point': node.start_point,
                'end_point':   node.end_point,
            })
        stack.extend(node.children)
    return branches


def get_condition_node(branch_node):
    """Extract the condition node from an if/for/while statement"""
    for child in branch_node.children:
        if child.type == 'parenthesized_expression':
            return child
    return None


def get_for_condition_node(for_node):
    """The condition of a for loop, or None if it has none (for(;;), for(i=0;;i++)).

    Only the Tree-sitter "condition" field. The old fallback took the first expression child
    when the field was missing, which is the initializer (i=0) or the update (i++) of a for
    without a condition: wrapping it would count the wrong expression."""
    return for_node.child_by_field_name("condition")


def get_for_condition_slot(for_node):
    """Byte offset of the ';' that ends the (empty) condition slot of a for loop.

    It is the last ';' child of the for node: for(;;) and for(i=0;;i++) have two ';' children,
    for(int i=0;;i++) has one (the declaration owns its own ';')."""
    semis = [c for c in for_node.children if c.type == ';']
    return semis[-1].start_byte if semis else None


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


def build_cover_chain(switch_meta, base_id, var):
    """The if/else if cover() chain for a switch, comparing `var` (the switch value, evaluated once).

    IDs follow label order (same as write_branch_map); a missing default gets the next ID.
    The default is checked last wherever its label is, because it is taken only when no case
    matches; a switch with only a default records cover(1, id). The implicit default (no
    default label) also records cover(1, id): every switch label edge is a true counter."""
    cases, default_id, parts = [], None, []
    for i, case in enumerate(switch_meta['cases']):
        if case['kind'] == 'case':
            cases.append((base_id + i, case['value']))
        else:
            default_id = base_id + i
    for k, (cid, value) in enumerate(cases):
        # parenthesised: switch (x & 3) case 1 must not become x & 3 == 1
        parts.append(f"{'if' if k == 0 else 'else if'} (cover(({var}) == ({value}), {cid})) ;")
    if default_id is not None:
        last = f"cover(1, {default_id});"
    else:
        last = f"cover(1, {base_id + len(switch_meta['cases'])});"
    parts.append(f"else {last}" if cases else last)
    return ' '.join(parts)


class SourceRewriter:
    """Collects edits as wraps (text before + text after a byte range) and applies them inside-out.

    Decisions can nest: a ?: inside an if condition gives a wrap inside a wrap. The inner wrap
    is applied first and the outer one wraps the result, so no decision is lost and no text is
    duplicated (the old replace-by-range version copied overlapping ranges twice).
    Edits must nest or be disjoint; a partial overlap raises ValueError.
    """

    def __init__(self, source: bytes):
        self.source = source
        self.edits  = []

    def wrap(self, start, end, before, after):
        self.edits.append((start, end, before, after))

    def insert(self, pos, text):
        self.wrap(pos, pos, text, '')

    def apply(self):
        src    = self.source
        parts  = [[]]       # parts[-1]: output of the innermost open wrap (parts[0]: whole file)
        opened = []         # (end, before, after) of open wraps, innermost last
        pos    = 0

        def close():
            nonlocal pos
            end, before, after = opened.pop()
            parts[-1].append(src[pos:end])
            pos = end
            inner = b''.join(parts.pop())
            parts[-1].append(before.encode() + inner + after.encode())

        # outer before inner when two edits start at the same byte
        for start, end, before, after in sorted(self.edits, key=lambda e: (e[0], -e[1])):
            while opened and opened[-1][0] <= start:
                close()
            if opened and end > opened[-1][0]:
                raise ValueError(f"overlapping edits at bytes {start}-{end}")
            parts[-1].append(src[pos:start])
            pos = start
            if start == end:
                parts[-1].append(before.encode() + after.encode())
                continue
            opened.append((end, before, after))
            parts.append([])
        while opened:
            close()
        parts[0].append(src[pos:])
        return b''.join(parts[0]).decode('utf-8')


def strip_verifier_boilerplate(code: str) -> str:
    simple_patterns = [
        r'extern\s+[^;]*__assert_fail[^;]*;',
        r'extern\s+[^;]*__assert_perror_fail[^;]*;',
        r'extern\s+[^;]*__assert\s*\([^;]*;',
        # No longer stripped: 'typedef unsigned int size_t;' (added in 310d799 because
        # cov_runtime.h then included <stdio.h>, whose LP64 size_t conflicted with it). Since
        # 24672ad the header includes nothing, and the program needs its own typedef.
    ]
    for pattern in simple_patterns:
        code = re.sub(pattern, '', code, flags=re.DOTALL)

    def remove_function_def(src, fname):
        """Drop the definition of void fname(...) { ... }. The '{' may be on the header line
        or on one of the next MAX_HELD lines (e.g. 'void reach_error()' then '{' below, as in
        recursified_nested_1b.c); a ';' first means a declaration, which is kept."""
        MAX_HELD = 5
        lines = src.split('\n')
        out = []
        skip = False
        depth = 0
        held = None          # header line(s) of a definition whose '{' has not been seen yet
        for line in lines:
            if held is not None:
                if '{' in line:
                    held, skip = None, True
                    depth = line.count('{') - line.count('}')
                    if depth <= 0:
                        skip = False
                elif ';' in line or len(held) >= MAX_HELD:
                    out.extend(held + [line])
                    held = None
                else:
                    held.append(line)
                continue
            if not skip:
                if re.search(rf'\bvoid\s+{fname}\s*\(', line) and '{' in line:
                    skip = True
                    depth = line.count('{') - line.count('}')
                    if depth <= 0:
                        skip = False
                    continue
                if re.search(rf'\bvoid\s+{fname}\s*\(', line) and ';' not in line:
                    held = [line]
                    continue
                out.append(line)
            else:
                depth += line.count('{') - line.count('}')
                if depth <= 0:
                    skip = False
        if held is not None:
            out.extend(held)
        return '\n'.join(out)  # ← always returns

    for fname in ['reach_error', '__VERIFIER_error']:
        code = remove_function_def(code, fname)

    return code  # ← always returns


def is_instrumentable(branch, source_code):
    """Single source of truth for which constructs get a cover() ID.

    Both instrument_code() and write_branch_map() iterate over the constructs this accepts,
    so the IDs in the instrumented source and the entries in branch_map.json cannot drift
    apart. A construct is skipped (consumes no ID, appears in no map) when there is nothing
    to wrap: a switch with no condition node or no case/default labels. A for without a
    condition (for(;;)) is instrumentable: cover((1), id) is inserted in its empty slot.
    """
    node = branch['node']
    kind = branch['type']
    if kind in ('if_statement', 'while_statement', 'do_statement'):
        return get_condition_node(node) is not None
    if kind == 'for_statement':
        return get_for_condition_node(node) is not None or get_for_condition_slot(node) is not None
    if kind == 'switch_statement':
        return get_condition_node(node) is not None and bool(get_switch_cases(node, source_code)['cases'])
    if kind == 'conditional_expression':
        cond = node.children[0] if node.children else None
        return cond is not None and source_code[cond.start_byte:cond.end_byte].decode('utf-8').strip() != ''
    return False


def instrumentable_branches(branches, source_code):
    """Branches that receive IDs, in source order."""
    return [b for b in sorted(branches, key=lambda b: b['start_byte']) if is_instrumentable(b, source_code)]


def pair_decisions(decisions, branches, source_code, path):
    """Pair each counted Clang decision with the Tree-sitter node to rewrite.

    Key: (kind, line, column) — Clang's expansion location and the start of the Tree-sitter
    node (both point at the keyword, or at the start of the condition for ?:).
    Returns (paired Tree-sitter branches, Tree-sitter constructs with no Clang decision).
    Raises PairingError if any decision has no node, or its node cannot be wrapped as Clang
    sees it (no condition, or a different number of case labels): instrumenting it anyway
    would silently count something else.
    """
    by_key = {}
    for b in sorted(branches, key=lambda b: b['start_byte']):
        key = (TS_KIND[b['type']], b['start_point'][0] + 1, b['start_point'][1] + 1)
        by_key.setdefault(key, []).append(b)

    paired, problems = [], []
    for d in decisions:
        key = (d['kind'], d['line'], d['col'])
        nodes = by_key.get(key)
        if not nodes:
            problems.append(f"{path}:{d['line']}:{d['col']}: {d['kind']}: Clang sees a decision here, "
                            f"Tree-sitter has no {d['kind']} node starting at this position")
            continue
        b = nodes.pop(0)
        if not is_instrumentable(b, source_code):
            problems.append(f"{path}:{d['line']}:{d['col']}: {d['kind']}: Tree-sitter node has no "
                            f"condition / case labels to wrap")
        elif d['kind'] == 'switch' and len(get_switch_cases(b['node'], source_code)['cases']) != d['n_cases']:
            n_ts = len(get_switch_cases(b['node'], source_code)['cases'])
            problems.append(f"{path}:{d['line']}:{d['col']}: switch: Clang counts {d['n_cases']} case "
                            f"labels, Tree-sitter finds {n_ts} (labels from macros or nested blocks?)")
        paired.append(b)
    if problems:
        raise PairingError(f"{len(problems)} decision(s) could not be paired:\n  " + '\n  '.join(problems))
    unpaired = [b for nodes in by_key.values() for b in nodes]
    return paired, unpaired


def instrument_code(source_code, branches, start_id=1):
    """Wrap branch conditions with cover() macro. start_id enables global IDs across files."""
    rewriter   = SourceRewriter(source_code)
    current_id = start_id

    for branch in instrumentable_branches(branches, source_code):
        branch_type = branch['type']
        node        = branch['node']

        if branch_type in ['if_statement', 'while_statement', 'do_statement']:
            condition_node = get_condition_node(node)
            if condition_node:
                cond_start     = condition_node.start_byte
                cond_end       = condition_node.end_byte
                # (cond) -> (cover((cond), id)): the condition keeps its own parentheses inside
                # cover(), so a top-level comma (while (f(), x)) cannot split the macro arguments.
                rewriter.wrap(cond_start, cond_end, "(cover(", f", {current_id}))")
                current_id += 1

        elif branch_type == 'for_statement':
            condition_node = get_for_condition_node(node)
            if condition_node:
                rewriter.wrap(condition_node.start_byte, condition_node.end_byte,
                              " cover((", f"), {current_id}) ")
            else:
                # for(;;) is counted like while(1): a decision whose condition is always true
                # (its false edge exists in the map but cannot be hit)
                rewriter.insert(get_for_condition_slot(node), f"cover((1), {current_id})")
            current_id += 1

        elif branch_type == 'switch_statement':
            # is_instrumentable() guarantees a condition node and at least one label
            switch_meta = get_switch_cases(node, source_code)
            condition_node = get_condition_node(node)
            # switch (E) -> switch (({ __typeof__((E) + 0) v = (E); <chain on v>; v; })):
            # E is evaluated once (a GNU statement expression; __typeof__ does not evaluate its
            # operand, and its copy of E is the original text, so it holds no cover() call).
            # (E) + 0 is the promoted type the switch itself uses, and works for bit-fields.
            var = f"__c2obra_sw_{current_id}"
            chain = build_cover_chain(switch_meta, current_id, var)
            rewriter.wrap(condition_node.start_byte, condition_node.end_byte,
                          f"(({{ __typeof__(({switch_meta['expression']}) + 0) {var} = ",
                          f"; {chain} {var}; }}))")
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
                    rewriter.wrap(cond_start, cond_end, "cover((", f"), {current_id})")
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
    """Write branch metadata to branch_map.json. Returns (next available branch ID, number of edges).

    "edges" lists every real edge, one entry per edge: {"id": cover() id, "side": "true"|"false"}.
    A decision (if, loop, ?:) has two edges. A switch label has one: its cover() is true when
    that label is taken; its false counter only means "not this label" and is not an edge.
    The implicit default is also recorded as cover(1, id) (build_cover_chain), so every switch
    label edge is a true side. edges.edge_coverage() turns this list into covered/total.
    """
    sorted_branches = instrumentable_branches(branches, source_code)
    branch_map  = []
    edges       = []
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
                edges.append({"id": current_id, "side": "true"})
                current_id += 1
            if not any(c['kind'] == 'default' for c in meta['cases']):
                branch_map.append({
                    "id":    current_id,
                    "line":  branch['start_point'][0] + 1,
                    "type":  "switch_implicit_default",
                    "label": "implicit default",
                })
                edges.append({"id": current_id, "side": "true"})
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
            edges += [{"id": current_id, "side": "true"}, {"id": current_id, "side": "false"}]
            current_id += 1

        elif branch_type == 'conditional_expression':
            branch_map.append({
                "id":          current_id,
                "line":        branch['start_point'][0] + 1,
                "type":        "ternary_expression",
                "true_label":  "ternary (true)",
                "false_label": "ternary (false)",
            })
            edges += [{"id": current_id, "side": "true"}, {"id": current_id, "side": "false"}]
            current_id += 1

        else:
            # for_statement, while_statement, do_statement
            branch_map.append({
                "id":   current_id,
                "line": branch['start_point'][0] + 1,
                "type": branch_type,
            })
            edges += [{"id": current_id, "side": "true"}, {"id": current_id, "side": "false"}]
            current_id += 1

    with open(output_file, 'w') as f:
        json.dump({
            "source_file": os.path.relpath(input_file),
            "branches":    branch_map,
            "edges":       edges,
        }, f, indent=2)
    print(f"✓ Wrote branch map to {output_file}")
    return current_id, len(edges)


def instrument_file(input_file, output_file, start_id=1, flags=None):
    """
    Instrument a single .c file. Returns (next available branch ID, number of edges).
    start_id allows global branch IDs across multiple files.
    flags: compiler flags shared with gcc (-D, -I, -std ...); None = DEFAULT_SVCOMP_FLAGS.
    """
    flags = DEFAULT_SVCOMP_FLAGS if flags is None else flags
    print(f"Instrumenting {input_file}...")

    if not os.path.exists(input_file):
        print(f"❌ Error: File '{input_file}' not found")
        sys.exit(1)
    if not input_file.endswith(('.c', '.i')):
        print(f"❌ Error: Expected a .c or .i file, got '{input_file}'")
        sys.exit(1)
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        print(f"❌ Error: Output directory '{output_dir}' does not exist")
        sys.exit(1)

    tree, source_code = parse_c_file(input_file)
    if tree.root_node.has_error:
        print("⚠️ Warning: Source file contains syntax errors — instrumentation may be incomplete")

    try:
        decisions, skipped = clang_scan.decisions(input_file, flags)
        branches, unpaired = pair_decisions(decisions, find_branches(tree), source_code, input_file)
    except (clang_scan.ClangScanError, PairingError) as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    for reason, n in sorted(skipped.items()):
        print(f"ℹ️ Skipped {n} Clang decision(s): {reason}")
    if unpaired:
        print(f"ℹ️ {len(unpaired)} Tree-sitter construct(s) have no Clang decision "
              f"(inactive #if arm, not compiled, or outside a function) — not instrumented")
    if not branches:
        print("⚠️ Warning: No branches found — output will be identical to input")
    else:
        print(f"✓ Found {len(branches)} decisions")

    instrumented_code = instrument_code(source_code, branches, start_id=start_id)

    try:
        with open(output_file, 'w') as f:
            f.write(instrumented_code)
        print(f"✓ Wrote {output_file}")
    except OSError as e:
        print(f"❌ Error writing output: {e}")
        sys.exit(1)

    map_file   = output_file.replace('.c', '_branch_map.json')
    next_id, n_edges = write_branch_map(branches, source_code, map_file, input_file, start_id=start_id)
    # Counters, not edges: cover() id N uses slots 2N-2 (true) and 2N-1 (false) in the runtime
    total_counters = (next_id - start_id) * 2
    print(f"BRANCH_COUNTERS={total_counters}")
    print(f"Done! Instrumented {len(branches)} decisions, {n_edges} branch edges.\n")
    return next_id, n_edges


def instrument_directory(input_dir, output_dir, flags=None):
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

    next_id, total_edges = 1, 0
    for input_file in c_files:
        rel_path    = os.path.relpath(input_file, input_dir)
        base_name   = os.path.splitext(rel_path)[0] + '_inst.c'
        output_file = os.path.join(output_dir, base_name)
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        next_id, n_edges = instrument_file(input_file, output_file, start_id=next_id, flags=flags)
        total_edges += n_edges

    total_ids = next_id - 1
    print(f"✅ Directory instrumentation complete.")
    print(f"   Files instrumented      : {len(c_files)}")
    print(f"   Total cover() IDs       : {total_ids}")
    print(f"   Total branch edges      : {total_edges}")
    print(f"BRANCH_COUNTERS={total_ids * 2}")


def print_flags(flags, given):
    """Every run says which flags the Clang scan used; the leniency flags are scan-only."""
    print(f"Compiler flags ({'from command line' if given else 'default for SV-COMP; pass -- <flags> to override'}): "
          f"{' '.join(flags) or '(none)'}")
    print(f"Scan-only flags: {' '.join(clang_scan.LENIENCY_FLAGS + clang_scan.CLANG_ONLY_FLAGS)} "
          f"-isystem <clang resource dir>/include")


def main():
    args, flags = sys.argv[1:], None
    if '--' in args:
        i = args.index('--')
        args, flags = args[:i], args[i + 1:]
    if len(args) == 2:
        input_path, output_path = args
        print_flags(DEFAULT_SVCOMP_FLAGS if flags is None else flags, flags is not None)

        if os.path.isdir(input_path):
            if not os.path.exists(output_path):
                os.makedirs(output_path, exist_ok=True)
            instrument_directory(input_path, output_path, flags=flags)
        else:
            instrument_file(input_path, output_path, start_id=1, flags=flags)
    else:
        print("Usage:")
        print("  Single file : python3 instrument.py <source.c> <output.c> [-- <compiler flags>]")
        print("  Directory   : python3 instrument.py <source_dir/> <output_dir/> [-- <compiler flags>]")
        print(f"  Without '--', the flags are {' '.join(DEFAULT_SVCOMP_FLAGS)} (SV-COMP default).")
        sys.exit(1)


if __name__ == "__main__":
    main()
