#!/usr/bin/env python3
"""
C²oBra - Source Instrumenter
Iteration 1: Basic branch instrumentation ->
Iteration 2: Switch instrumentation + error handling + multi-file directory support ->
Iteration 3: Explicit else branch metadata tracking
Iteration 2: Clang (clang_scan.py) decides which decisions exist AND where their conditions are;
this file only turns those byte spans into cover() calls. Tree-sitter is no longer used.
"""


import sys, json, os, re, time
from collections import Counter
import clang_scan


# Verifier boilerplate that conflicts with verifier_stubs.c at link time
# These are stripped from instrumented output
# Flags used when the caller gives none (no "--" on the command line). SV-COMP files use
# LARGE_INT without defining it; the pipeline's gcc gets it from cov_runtime.h (same value).
DEFAULT_SVCOMP_FLAGS = ['-DLARGE_INT=1000000']

# Clang decision kind (clang_scan.KINDS) -> the "type" used for a branch here and in branch_map.json
TYPE_OF_KIND = {'if': 'if_statement', 'for': 'for_statement', 'while': 'while_statement',
                'do': 'do_statement', 'switch': 'switch_statement', '?:': 'conditional_expression'}


class PairingError(Exception):
    """A Clang decision has no plain-text span to wrap (e.g. its condition is inside a macro argument),
    or two cover() wraps would partly overlap."""


VERIFIER_STUB_PATTERNS = [
    r'void\s+reach_error\s*\([^)]*\)\s*\{[^}]*\}',
    r'void\s+__VERIFIER_error\s*\([^)]*\)\s*\{[^}]*\}',
    r'extern\s+[^;]*__assert_fail[^;]*;',
]


def build_cover_chain(switch_meta, base_id, var):
    """The if/else if cover() chain for a switch, comparing `var` (the switch value, evaluated once).

    IDs follow label order (same as write_branch_map); a missing default gets the next ID.
    The default is checked last wherever its label is, because it is taken only when no case
    matches; a switch with only a default records cover(1, id). The implicit default (no
    default label) also records cover(1, id): every switch label edge is a true counter."""
    cases, default_id, parts = [], None, []
    for i, case in enumerate(switch_meta['cases']):
        if case['kind'] == 'case':
            cases.append((base_id + i, case['value'], case.get('high')))
        else:
            default_id = base_id + i
    for k, (cid, value, high) in enumerate(cases):
        # parenthesised: switch (x & 3) case 1 must not become x & 3 == 1
        test = f"({var}) == ({value})" if high is None else f"(({var}) >= ({value}) && ({var}) <= ({high}))"
        parts.append(f"{'if' if k == 0 else 'else if'} (cover({test}, {cid})) ;")
    if default_id is not None:
        last = f"cover(1, {default_id});"
    else:
        last = f"cover(1, {base_id + len(switch_meta['cases'])});"
    parts.append(f"else {last}" if cases else last)
    return ' '.join(parts)


class OverlapError(ValueError):
    """Two edits partly overlap (neither nested nor disjoint); start/end: the second one's bytes."""

    def __init__(self, start, end):
        super().__init__(f"overlapping edits at bytes {start}-{end}")
        self.start, self.end = start, end


class SourceRewriter:
    """Collects edits as wraps (text before + text after a byte range) and applies them inside-out.

    Decisions can nest: a ?: inside an if condition gives a wrap inside a wrap. The inner wrap
    is applied first and the outer one wraps the result, so no decision is lost and no text is
    duplicated (the old replace-by-range version copied overlapping ranges twice).
    Edits must nest or be disjoint; a partial overlap raises OverlapError (a ValueError).
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
                raise OverlapError(start, end)
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


def branch_from_decision(d, source_code):
    """A branch (what instrument_code() and write_branch_map() work on) from one counted Clang
    decision (clang_scan.decisions()), or a list of problems if its condition has no plain
    text to wrap. Returns (branch, None) or (None, reason)."""
    kind = d['kind']
    branch = {
        'type':        TYPE_OF_KIND[kind],
        'start_byte':  d['offset'],
        'start_point': (d['line'] - 1, d['col'] - 1),
        'cond_span':   d['cond_span'],
        'slot':        None,
        'else_info':   d.get('else_info'),
        'switch':      None,
    }
    if kind == 'for' and d['cond_span'] is None:
        # only a for without condition has a slot to fill, at the header's second ';'
        if d['has_condition'] is not False or not d.get('for_semis'):
            return None, "no plain-text condition span (macro argument or inside a macro?)"
        branch['slot'] = d['for_semis'][1]
    elif d['cond_span'] is None:
        return None, "no plain-text condition span (macro argument or inside a macro?)"
    if kind == 'switch':
        cases = []
        for c in d['cases']:
            if c['kind'] == 'default':
                cases.append({'kind': 'default', 'line': c['line']})
            elif c['span'] is None or (c['is_range'] and c['range_hi'] is None):
                return None, "a case label is not plain text (macro argument?)"
            else:
                value = source_code[c['span'][0]:c['span'][1]].decode('utf-8').strip()
                case = {'kind': 'case', 'value': value, 'line': c['line']}
                if c['is_range']:       # GNU 'case lo ... hi:'
                    case['high'] = source_code[c['range_hi'][0]:c['range_hi'][1]].decode('utf-8').strip()
                cases.append(case)
        expr = source_code[d['cond_span'][0]:d['cond_span'][1]].decode('utf-8').strip()
        branch['switch'] = {'expression': expr, 'cases': cases}
    return branch, None


def build_branches(decisions, source_code, path):
    """Branches for all counted Clang decisions, in source order. Raises PairingError listing
    every decision that cannot be wrapped: instrumenting around it would count something else."""
    branches, problems = [], []
    for d in decisions:
        b, why = branch_from_decision(d, source_code)
        if b is None:
            problems.append(f"{path}:{d['line']}:{d['col']}: {d['kind']}: {why}")
        else:
            branches.append(b)
    if problems:
        # "could not be paired": scripts/batch/stages.py and docs/mass_test.md match this text
        raise PairingError(f"{len(problems)} decision(s) could not be paired with a plain-text condition:\n  " + '\n  '.join(problems))
    return sorted(branches, key=lambda b: b['start_byte'])


def instrument_code(source_code, branches, start_id=1):
    """Wrap branch conditions with cover() macro. start_id enables global IDs across files."""
    rewriter   = SourceRewriter(source_code)
    current_id = start_id

    for branch in branches:
        branch_type = branch['type']
        span        = branch['cond_span']

        if branch_type in ('if_statement', 'while_statement', 'do_statement'):
            # if (cond) -> if (cover((cond), id)): the condition keeps its own parentheses inside
            # cover(), so a top-level comma (while (f(), x)) cannot split the macro arguments.
            rewriter.wrap(*span, "cover((", f"), {current_id})")
            current_id += 1

        elif branch_type == 'for_statement':
            if span is not None:
                rewriter.wrap(*span, " cover((", f"), {current_id}) ")
            else:
                # for(;;) is counted like while(1): a decision whose condition is always true
                # (its false edge exists in the map but cannot be hit)
                rewriter.insert(branch['slot'], f"cover((1), {current_id})")
            current_id += 1

        elif branch_type == 'switch_statement':
            switch_meta = branch['switch']
            # switch (E) -> switch (({ __typeof__((E) + 0) v = (E); <chain on v>; v; })):
            # E is evaluated once (a GNU statement expression; __typeof__ does not evaluate its
            # operand, and its copy of E is the original text, so it holds no cover() call).
            # (E) + 0 is the promoted type the switch itself uses, and works for bit-fields.
            var = f"__c2obra_sw_{current_id}"
            chain = build_cover_chain(switch_meta, current_id, var)
            rewriter.wrap(*span,
                          f"({{ __typeof__(({switch_meta['expression']}) + 0) {var} = (",
                          f"); {chain} {var}; }})")
            has_default = any(c['kind'] == 'default' for c in switch_meta['cases'])
            current_id += len(switch_meta['cases']) + (0 if has_default else 1)

        elif branch_type == 'conditional_expression':
            # ternary: condition ? true_expr : false_expr
            rewriter.wrap(*span, "cover((", f"), {current_id})")
            current_id += 1

    try:
        code = rewriter.apply()
    except OverlapError as e:
        line = source_code.count(b'\n', 0, e.start) + 1
        col = e.start - (source_code.rfind(b'\n', 0, e.start) + 1) + 1
        raise PairingError(
            f"{line}:{col}: two cover() wraps partly overlap (bytes {e.start}-{e.end}): a condition "
            f"span crosses another decision's span (a macro or a GNU statement "
            f"expression?); the output would be broken")
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
    sorted_branches = sorted(branches, key=lambda b: b['start_byte'])
    branch_map  = []
    edges       = []
    current_id  = start_id

    for branch in sorted_branches:
        branch_type = branch['type']
        if branch_type == 'switch_statement':
            meta = branch['switch']
            for case in meta['cases']:
                label = (f"case {case['value']}" + (f" ... {case['high']}" if 'high' in case else '')
                         if case['kind'] == 'case' else 'default')
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
            has_else, else_line, is_else_if = branch['else_info']

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

    t0 = time.perf_counter()
    with open(input_file, 'rb') as f:
        source_code = f.read()

    try:
        decisions, skipped = clang_scan.decisions(input_file, flags)
        t_parse = time.perf_counter() - t0                 # Clang scan
        branches = build_branches(decisions, source_code, input_file)
    except (clang_scan.ClangScanError, PairingError) as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    for reason, n in sorted(skipped.items()):
        print(f"ℹ️ Skipped {n} Clang decision(s): {reason}")
    if not branches:
        print("⚠️ Warning: No branches found — output will be identical to input")
    else:
        print(f"✓ Found {len(branches)} decisions")

    try:
        instrumented_code = instrument_code(source_code, branches, start_id=start_id)
    except PairingError as e:
        print(f"❌ Error: {input_file}:{e}")
        sys.exit(1)

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
    write_timing(t_parse, time.perf_counter() - t0 - t_parse)
    return next_id, n_edges


def write_timing(parse, instrument):
    """Seconds of the parse (the Clang scan) and of the rest (pairing, rewriting, writing
    the files) to $C2OBRA_TIMING_FILE as JSON; nothing if it is not set (scripts/batch/mass_test.py sets it)."""
    path = os.environ.get('C2OBRA_TIMING_FILE')
    if path:
        with open(path, 'w') as f:
            json.dump({'parse': round(parse, 4), 'instrument': round(instrument, 4)}, f)


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
    print(f"Scan-only flags for a .i file: {' '.join(clang_scan.PREPROCESSED_FLAGS)}")


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
