# `report.py --mode testcov`: TestCov's goals from C²oBra's counters

```
python3 src/report.py <file>_inst_branch_map.json <coverage.json> --mode testcov \
    [--source <original .c>] [--csv goals.csv]
```

Same tests, same instrumentation, same counters as the default mode; only the denominator and
the count follow TestCov's goal definition instead of C²oBra's edge definition. The mode writes
one CSV row per goal plus a `SUMMARY` row (`covered/total goals (pct)`), prints the totals, and
writes no HTML. Without `--mode`, report.py and its output are unchanged (HTML, CSV and source
view compared with `main` on d02, d10 and d11: identical apart from the generation time).
Code: `src/testcov_goals.py`. Tests: `unittests/test_testcov_mode.py`.

## Where the definition comes from

TestCov's instrumented copies of the 15 definition programs and its numbers with one empty test
(`tests/definition/testcov_results/`, testcov-sikraken `26db1c6`, 2026-10-26). TestCov writes a
goal label (`Goal_N:;`) at the start of each block and after each loop and case label:

| construct | TestCov goals | from C²oBra's counters |
|---|---|---|
| `if` | then-block, else-block (an empty `else {}` is added when there is none) | true side, false side |
| `if … else if` | no goal for the outer false side; the inner `if` has its own goals | true side only |
| `?:` | both arms | true side, false side |
| `while`, `for` (also `while(1)`, `for(;;)`) | body start, statement after the loop | true side; false side **or** a break of the loop (see below) |
| `do … while` | statement after the loop only, no repeat goal | false side **or** a break of the loop |
| `switch` | after each `case`/`default` label in the source; no implicit default | label selected **or** the label before it falls through and was reached |
| `&&`, `\|\|` | none of their own (one `if`) | — |
| decisions from a macro | counted by TestCov (it works on the preprocessed text) | **not counted**: no counters in a `.c` file |

Two goals need facts the counters do not hold; `testcov_goals.py` reads them from the original
source with Tree-sitter (no change to the instrumentation or to the branch map):

- **A break of the loop.** The break is credited when the edge of the innermost `if` around it
  (inside the loop) was taken; a break with no `if` around it, when the loop ran. Breaks of a
  nested loop or `switch` are not the loop's.
- **Fall-through.** A label falls through into the next one when its statements are empty
  (stacked labels) or do not end with `break`, `return`, `continue` or `goto`.

Each branch-map entry is paired with its Tree-sitter node by (type, line), in source order.

## Result on tests/definition

| program | edges (default mode) | TestCov measured | `--mode testcov` | |
|---|---|---|---|---|
| d01_if | 3/4 | 3/4 | 3/4 | match |
| d02_else_if | 3/4 | 2/3 | 2/3 | match |
| d03_while | 3/4 | 3/4 | 3/4 | match |
| d04_for | 2/2 | 2/2 | 2/2 | match |
| d05_do_while | 3/4 | 2/2 | 2/2 | match |
| d06_while1 | 3/4 | 4/4 | 4/4 | match |
| d07_for_infinite | 3/4 | 4/4 | 4/4 | match |
| d08_ternary | 3/4 | 3/4 | 3/4 | match |
| d09_switch_default | 3/3 | 3/3 | 3/3 | match |
| d10_switch_no_default | 2/3 | 2/2 | 2/2 | match |
| d11_switch_fallthrough | 1/3 | 2/3 | 2/3 | match |
| d12_switch_stacked | 2/4 | 3/3 | 3/3 | match |
| d13_switch_side_effect | 1/3 | 1/2 | 1/2 | match |
| d14_logical_ops | 2/2 | 2/2 | 2/2 | match |
| d15_macros | 1/2 | error | 1/2 | no TestCov number |

All 14 programs with a TestCov number match: the 6 where TestCov already agreed with the edge
count (d01, d03, d04, d08, d09, d14) and the 8 where it did not. **d15** has no number to match:
TestCov's own instrumentation does not compile (`'else' without a previous 'if'`,
`testcov_results/d15_macros/testcov.log`). The mode gives 1/2 there, because the 3 decisions that
come from macros are skipped by instrument.py and have no counters; TestCov would count them.

What is compared: the totals (covered/total) per program, the only numbers TestCov reports. For
d02, d05, d06, d10, d11 and d12 the test also checks which goals are reached, against the goal
positions in TestCov's instrumented copies. TestCov's per-goal results are not available, so
which goals TestCov itself counted as reached was not compared.

## Not matched / not exact

- **Macro decisions** (d15 and any `.c` file with them): TestCov counts them, the mode cannot (no
  counters). In a `.i` input they are plain text and are instrumented, so they are counted there.
- **Break credit is static.** Code between the controlling edge and the `break` is not looked at:
  `if (c) { if (d) return 0; break; }` credits the break whenever `c` was true, even if every
  run returned first. A break directly in a `do` body before the condition is ever evaluated is
  not seen (the loop's counters are 0).
- **Fall-through is static.** A label whose statements end in an `if` or a block is taken to fall
  through, whether or not it did at run time.
- **Only the constructs above** were checked against TestCov (the 15 programs). Not checked:
  `goto` targets, labels inside nested blocks of a case, a `switch` without braces, statement
  expressions, nested functions. Whether TestCov adds goals elsewhere in larger programs (for
  example at function entry) was not checked; none of the 15 programs shows one.
- **Branch-map entries without a Tree-sitter node** (decisions Clang found in a header with a GNU
  statement expression) get no goal; they are printed as unmatched.
- **No HTML** in this mode, only the CSV and the printed totals.
