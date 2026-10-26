# Behaviour preservation on the corpus

Date: 2026-10-26. Written by `tests/test_behaviour.py` (`C2OBRA_BEHAVIOUR_MD=1`).

Original and instrumented program compiled with gcc, run with no input (stdin `/dev/null`) and a 5 s timeout; stdout and exit status compared.

Tools:

- gcc: `gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`
- clang (resource dir for the scan): `Ubuntu clang version 18.1.3 (1ubuntu1)`
- libclang (Python, used by the scan): `18.1.1`

PASS 33, FAIL 1 (1 known bug), SKIP 9 (of 43 checks)

| program | result | reason |
|---|---|---|
| corpusC/c01 (with driver) | PASS |  |
| corpusC/c02 (with driver) | PASS |  |
| corpusC/c03 (with driver) | PASS |  |
| corpusC/c03 (with driver) -DFAST | PASS |  |
| corpusC/c04 (with driver) | PASS |  |
| corpusC/c05 (with driver) | PASS |  |
| corpusC/c05 (with driver) -DDEBUG | PASS |  |
| corpusC/c06 (with driver) | PASS |  |
| corpusC/c07 (with driver) | SKIP | instrument.py stopped: ❌ Error: 1 decision(s) could not be paired: |
| corpusC/c08 (with driver) | PASS |  |
| corpusC/c09 (with driver) | FAIL | known bug: GNU case range `case 1 ... 5:` (tree-sitter-c 0.21.3 makes `... 5` an ERROR node, get_switch_cases() uses it as the value). instrumented copy does not compile: c09_gnu_extensions_inst.c:11:85: error: expected expression before ‘...’ token |
| corpusC/c10 (with driver) | PASS |  |
| corpusC/c11 (with driver) | PASS |  |
| corpusC/c12 (with driver) | PASS |  |
| corpusC/c13 (with driver) | PASS |  |
| corpusC/c14 (with driver) | PASS |  |
| corpusC/c15_switch_side_effect.c | PASS |  |
| examples/simple_if.c | SKIP | nondeterministic input (__VERIFIER_nondet_*) |
| loop-simple/deep-nested.c | SKIP | timeout: original runs longer than 5 s |
| loop-simple/nested_1.c | PASS |  |
| loop-simple/nested_2.c | PASS |  |
| loop-simple/nested_3.c | PASS |  |
| loop-lit/bhmr2007.c | SKIP | nondeterministic input (__VERIFIER_nondet_*) |
| loop-lit/css2003.c | SKIP | nondeterministic input (__VERIFIER_nondet_*) |
| loop-lit/ddlm2013.c | SKIP | nondeterministic input (__VERIFIER_nondet_*) |
| loop-lit/gcnr2008.c | SKIP | nondeterministic input (__VERIFIER_nondet_*) |
| loop-lit/hhk2008.c | SKIP | nondeterministic input (__VERIFIER_nondet_*) |
| loop-lit/jm2006.c | SKIP | nondeterministic input (__VERIFIER_nondet_*) |
| definition/d01_if.c | PASS |  |
| definition/d02_else_if.c | PASS |  |
| definition/d03_while.c | PASS |  |
| definition/d04_for.c | PASS |  |
| definition/d05_do_while.c | PASS |  |
| definition/d06_while1.c | PASS |  |
| definition/d07_for_infinite.c | PASS |  |
| definition/d08_ternary.c | PASS |  |
| definition/d09_switch_default.c | PASS |  |
| definition/d10_switch_no_default.c | PASS |  |
| definition/d11_switch_fallthrough.c | PASS |  |
| definition/d12_switch_stacked.c | PASS |  |
| definition/d13_switch_side_effect.c | PASS |  |
| definition/d14_logical_ops.c | PASS |  |
| definition/d15_macros.c | PASS |  |
