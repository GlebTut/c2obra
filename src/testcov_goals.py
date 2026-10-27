#!/usr/bin/env python3
"""TestCov's goal definition, computed from C²oBra's counters (report.py --mode testcov).

Same tests, same instrumentation, same counters: only what is counted changes. The rules are
read off TestCov's instrumented copies of tests/definition/d01-d14
(tests/definition/testcov_results/, testcov-sikraken 26db1c6); TestCov puts a goal label at:

  if          the start of the then-block and of the else-block; TestCov adds an empty else
              block when there is none. An else-if has no goal of its own for the outer false
              side (the inner if's goals cover it): 1 goal + the inner if's.
  ?:          both arms (2 goals).
  while, for  the start of the body (counter: true side) and the statement after the loop,
              reached by the condition's false side or by a break of this loop.
  do-while    only the statement after the loop (no goal for the repeat).
  switch      after each case/default label written in the source, reached when that label is
              selected or when the label before it falls through into it. No goal for the
              implicit default.

Two goals need facts the counters do not hold; they are read from the source with Tree-sitter:
  - a break of the loop: the break is credited when the edge of the innermost if around it
    (inside the loop) was taken; a break with no if around it, when the loop body was entered.
    Approximation: code between that edge and the break (a return, exit(), a nested if that
    leaves) is not looked at.
  - a label falls through when the statements of the label before it are empty or do not end
    with break / return / continue / goto. Approximation: a body ending in an if or a block is
    taken to fall through.
Decisions that come from a macro have no counters in a .c file (instrument.py skips them), so
TestCov's goals for them cannot be counted here; they are not in the total.

goals() pairs each branch-map entry with its Tree-sitter node by (type, line), in source order.
An entry without a node (Clang-only decisions, e.g. headers with a statement expression) is
returned in 'unmatched' and adds no goal.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import instrument as I

MAP_TYPE = {'if_statement': 'if_statement', 'while_statement': 'while_statement',
            'for_statement': 'for_statement', 'do_statement': 'do_statement',
            'conditional_expression': 'ternary_expression', 'case_statement': 'switch_case'}
LOOPS = ('while_statement', 'for_statement', 'do_statement')
JUMPS = ('break_statement', 'return_statement', 'continue_statement', 'goto_statement')


def _nodes_by_key(root):
    """{(map type, line): [nodes in source order]}."""
    idx, stack = {}, [root]
    while stack:
        n = stack.pop()
        t = MAP_TYPE.get(n.type)
        if t:
            idx.setdefault((t, n.start_point[0] + 1), []).append(n)
        stack.extend(reversed(n.children))
    return idx


def _inside(node, ancestor):
    while node is not None:
        if node == ancestor:
            return True
        node = node.parent
    return False


def _loop_breaks(loop):
    """break statements that leave this loop (not those of a nested loop or switch)."""
    out, stack = [], [loop.child_by_field_name('body')]
    while stack:
        n = stack.pop()
        if n is None:
            continue
        if n.type == 'break_statement':
            out.append(n)
        elif n.type not in LOOPS + ('switch_statement',):
            stack.extend(n.children)
    return out


def _falls_through(case_node):
    """The statements of this label run into the next label (static, see the module doc)."""
    body = [c for c in case_node.named_children
            if c != case_node.child_by_field_name('value') and c.type != 'comment']
    return not body or body[-1].type not in JUMPS


def goals(branch_map, coverage, source_path):
    """{'goals': [{kind, line, id, reached}], 'covered', 'total', 'unmatched': [map entries]}.
    coverage: {id: {"true": n, "false": n}} as for edges.edge_coverage()."""
    tree, _ = I.parse_c_file(source_path)
    idx = _nodes_by_key(tree.root_node)
    node_of, id_of, unmatched = {}, {}, []
    for b in sorted(branch_map.get('branches', []), key=lambda b: b['id']):
        if b['type'] == 'switch_implicit_default':
            continue
        nodes = idx.get((b['type'], b['line']))
        if not nodes:
            unmatched.append(b)
            continue
        n = nodes.pop(0)
        node_of[b['id']], id_of[n.id] = n, b['id']

    def hit(bid, side):
        return coverage.get(bid, coverage.get(str(bid), {})).get(side, 0) > 0

    def break_taken(brk, loop, loop_id):
        n = brk.parent
        while n is not None and n != loop:
            if n.type == 'if_statement' and n.id in id_of:
                side = 'true' if _inside(brk, n.child_by_field_name('consequence')) else 'false'
                return hit(id_of[n.id], side)
            n = n.parent
        return hit(loop_id, 'true') or hit(loop_id, 'false')        # break directly in the body

    out = []

    def goal(kind, bid, reached):
        out.append({'kind': kind, 'line': node_of[bid].start_point[0] + 1, 'id': bid, 'reached': bool(reached)})

    switches = {}
    for bid, n in sorted(node_of.items()):
        t = n.type
        if t == 'if_statement':
            goal('if then', bid, hit(bid, 'true'))
            alt = n.child_by_field_name('alternative')
            if not (alt is not None and any(c.type == 'if_statement' for c in alt.named_children)):
                goal('if else', bid, hit(bid, 'false'))
        elif t == 'conditional_expression':
            goal('?: true', bid, hit(bid, 'true'))
            goal('?: false', bid, hit(bid, 'false'))
        elif t in LOOPS:
            if t != 'do_statement':
                goal('loop body', bid, hit(bid, 'true'))
            after = hit(bid, 'false') or any(break_taken(b, n, bid) for b in _loop_breaks(n))
            goal('after loop', bid, after)
        elif t == 'case_statement':
            switches.setdefault(n.parent.id, []).append((n.start_byte, bid, n))
    for labels in switches.values():
        prev_reached, prev_node = False, None
        for _, bid, n in sorted(labels):
            reached = hit(bid, 'true') or (prev_node is not None and prev_reached and _falls_through(prev_node))
            goal('case label', bid, reached)
            prev_reached, prev_node = reached, n
    out.sort(key=lambda g: (g['line'], g['id']))
    covered = sum(g['reached'] for g in out)
    return {'goals': out, 'covered': covered, 'total': len(out), 'unmatched': unmatched}
