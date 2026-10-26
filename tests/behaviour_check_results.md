# Behaviour preservation on the corpus

Date: 2026-10-26. Written by `tests/test_behaviour.py` (`C2OBRA_BEHAVIOUR_MD=1`).

Original and instrumented program compiled with gcc, run with no input (stdin `/dev/null`) and a 5 s timeout; stdout and exit status compared.

Tools:

- gcc: `gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`
- clang (resource dir for the scan): `Ubuntu clang version 18.1.3 (1ubuntu1)`
- libclang (Python, used by the scan): `18.1.1`

PASS 19, FAIL 0, SKIP 22 (of 41 programs)

| program | result | reason |
|---|---|---|
| corpusC/c01_macro_with_if.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c02_macro_condition_and_keyword.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c03_ifdef_split_braces.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c04_dead_code.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c05_flag_dependent.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c06_macro_loop_keyword.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c07_xmacro_switch.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c08_ternary_macros.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c09_gnu_extensions.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c10_include_header.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c11_kr_and_oddities.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c12_splices_comments.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c13_typedef_ambiguity.c | SKIP | original does not compile: undefined reference to `main' |
| corpusC/c14_short_circuit.c | SKIP | original does not compile: undefined reference to `main' |
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
