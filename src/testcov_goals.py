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

Two goals need facts the counters do not hold. instrument.py reads them from Clang while it
scans the file and stores them in the branch map, so this module needs only the map and the
counters (no source file, no second parse):
  - a break of the loop ("breaks" of a loop entry): the break is credited when the edge of the
    innermost if around it (inside the loop) was taken; a break with no if around it, when the
    loop body was entered. Approximation: code between that edge and the break (a return,
    exit(), a nested if that leaves) is not looked at.
  - a label falls through ("falls_through" of a switch_case entry) when the statements of the
    label are empty or do not end with break / return / continue / goto. Approximation: a body
    ending in an if or a block is taken to fall through.
Decisions that come from a macro have no counters in a .c file (instrument.py skips them), so
TestCov's goals for them cannot be counted here; they are not in the total.
"""

LOOPS = ('while_statement', 'for_statement', 'do_statement')


class MissingGoalFactsError(ValueError):
    pass


def goals(branch_map, coverage, source_path=None):
    """{'goals': [{kind, line, id, reached}], 'covered', 'total'}.
    coverage: {id: {"true": n, "false": n}} as for edges.edge_coverage().
    source_path is accepted for old callers and not used."""
    entries = [b for b in sorted(branch_map.get('branches', []), key=lambda b: b['id'])
               if b['type'] != 'switch_implicit_default']

    def hit(bid, side):
        return coverage.get(bid, coverage.get(str(bid), {})).get(side, 0) > 0

    def break_taken(brk, loop_id):
        if 'if' in brk:
            return hit(brk['if'], brk['side'])
        return hit(loop_id, 'true') or hit(loop_id, 'false')        # break directly in the body

    out = []

    def goal(kind, b, reached):
        out.append({'kind': kind, 'line': b['line'], 'id': b['id'], 'reached': bool(reached)})

    switches = {}
    for b in entries:
        t, bid = b['type'], b['id']
        if t == 'if_statement':
            goal('if then', b, hit(bid, 'true'))
            if b.get('false_label') != 'else if →':        # an else-if: the inner if has the goals
                goal('if else', b, hit(bid, 'false'))
        elif t == 'ternary_expression':
            goal('?: true', b, hit(bid, 'true'))
            goal('?: false', b, hit(bid, 'false'))
        elif t in LOOPS:
            if 'breaks' not in b:
                raise MissingGoalFactsError(
                    'branch map has no "breaks" for a loop (written by an older instrument.py) — '
                    're-run src/instrument.py to regenerate it')
            if t != 'do_statement':
                goal('loop body', b, hit(bid, 'true'))
            goal('after loop', b, hit(bid, 'false') or any(break_taken(x, bid) for x in b['breaks']))
        elif t == 'switch_case':
            if 'falls_through' not in b:
                raise MissingGoalFactsError(
                    'branch map has no "falls_through" for a switch label (written by an older '
                    'instrument.py) — re-run src/instrument.py to regenerate it')
            switches.setdefault(b['switch_id'], []).append(b)
    for labels in switches.values():
        prev_reached, prev = False, None
        for b in sorted(labels, key=lambda b: b['id']):
            reached = hit(b['id'], 'true') or (prev is not None and prev_reached and prev['falls_through'])
            goal('case label', b, reached)
            prev_reached, prev = reached, b
    out.sort(key=lambda g: (g['line'], g['id']))
    covered = sum(g['reached'] for g in out)
    return {'goals': out, 'covered': covered, 'total': len(out)}
