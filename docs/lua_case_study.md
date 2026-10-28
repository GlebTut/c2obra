# Case study: Lua 5.4.9 end to end through C²oBra

Date: 2026-10-26. Machine: Ubuntu 24.04 (WSL2), gcc 13.3.0, clang 18.1.3, libclang 18.1.1.
Time-box: about 2 hours. Took about 1 hour; nothing blocked for more than 30 minutes.

## Result

Lua 5.4.9, built from the instrumented sources, passes Lua's own test suite (basic mode) exactly as
the unmodified build does, and C²oBra reports:

| | |
|---|---|
| Files of the `lua` binary | 33 (`CORE_O`, `LIB_O`, `LUA_O` of `src/Makefile`) |
| Instrumented | 32 (`ltm.c` compiled uninstrumented, see problem 2) |
| Decisions | 1809 |
| `cover()` ids | 2436 (a switch label has its own id) |
| Edges | 4156 |
| Covered edges | 3681 |
| **Branch coverage** | **88.57 %** (3681 / 4156) |
| Decisions skipped (from a macro expansion) | 516, not in the edge total |
| Test suite, unmodified build | exit 0, `final OK !!!`, 26 test files, 0.31 s |
| Test suite, instrumented build | exit 0, `final OK !!!`, the same 26 files, 0.42 s |

The numbers come from `edges.edge_coverage()` per file; `merge_reports.py` shows the same total
(3681/4156, 88.6 %) in `summary_report.html`. One suite run, not repeated.

Cross-check with another tool (not the same metric): gcc `--coverage -O0` + `gcov -b` on the same
32 files and the same suite run gives 5233 of 6151 branches taken at least once (85.1 %). gcov counts
every `&&` / `||` operand and the code of macro expansions as branches; C²oBra counts decisions
(README "Coverage Model") and skips macro decisions, so the two totals differ by definition.

## How to reproduce

```
venv/bin/python3 scripts/batch/lua_e2e.py --work ~/benchmarks/lua/e2e \
    --lua-tar ~/benchmarks/lua/dl/lua-5.4.9.tar.gz --tests-tar ~/benchmarks/lua/dl/lua-5.4.9-tests.tar.gz
```

The tarballs were downloaded from https://www.lua.org/ftp/lua-5.4.9.tar.gz and
https://www.lua.org/tests/lua-5.4.9-tests.tar.gz (the test suite of 2026-08-10). The script checks
their sha256 against the values on those pages (`2335b6c5…`, `7d971845…`) and writes
`<work>/e2e.log`, `summary.json` (all numbers, per file), the two suite logs, and
`report/` (per-file HTML/CSV reports and `summary_report.html`).

## Steps

1. **Download and check.** Latest 5.4 release on lua.org: 5.4.9, with a matching test suite.
   Both sha256 values match the ones published on lua.org.
2. **Baseline.** `make linux` builds Lua unchanged in 5 s. Its flags (from `src/Makefile`):
   `gcc -std=gnu99 -O2 -Wall -Wextra -DLUA_COMPAT_5_3 -DLUA_USE_LINUX`, linked with
   `-lm -Wl,-E -ldl`.
3. **Choose the test inputs.** The suite's basic mode `lua -e"_U=true" all.lua` (in `testes/`) passes
   on the baseline (problem 1 explains why not the full mode). The C libraries in `testes/libs` are
   built with their own makefile against the Lua headers.
4. **Instrument.** The 33 files of the `lua` binary are instrumented one by one with
   `instrument.instrument_file()`, with global ids (`start_id` of each file = next free id) and the
   flags that change the program text: `-std=gnu99 -DLUA_COMPAT_5_3 -DLUA_USE_LINUX`. `luac.c` is not
   part of the `lua` binary and is left out. Instrumenting takes about 3 s.
5. **Build.** Each instrumented file is compiled with the Makefile's flags plus
   `-DMAX_BRANCHES=4872` (2 × ids), `-I` Lua's `src/` and C²oBra's `src/`, then linked with
   `cov_runtime.c` and the Makefile's libraries (4.5 s). `verifier_stubs.c` is not needed (no
   `__VERIFIER_*` calls).
6. **Run.** The suite runs with the instrumented `lua`. A wrapper script named `lua` sets
   `COVERAGE_OUTPUT=<work>/cov/cov.<pid>.json` and `exec -a "$0"`s the real binary, so every Lua
   process (also one started by a test) would write its own file. In basic mode only one process
   ran (1 coverage file).
7. **Report.** The counters of all coverage files are added up per id; for each file, the ids of
   its branch map are written as `<file>_inst_coverage.json`, then `report.py` (per file) and
   `merge_reports.py` (summary) are run unchanged.

## Problems

1. **The full test suite fails on the unmodified build (not a C²oBra problem).** `lua all.lua`
   without `_U` also runs `main.lua` (the stand-alone interpreter tests). It first needs the C
   libraries of `testes/libs` (built in step 3), then still stops at `main.lua:385`
   (`assertion failed!`, the test of a non-string `_PROMPT` with `lua -i`) on the baseline. Not
   investigated further; the basic mode (`_U=true`, which sets `_soft`, `_port`, `_nomsg`) was used.
   So `main.lua`, the heavy tests and the parts that need the internal test library (`ltests`, `T`)
   are not run, and `lua.c` (the stand-alone interpreter) is the least covered file (25.5 %).
2. **`ltm.c` cannot be instrumented: known limitation (pairing error).**
   `ltm.c:206:8: if: Clang sees a decision here, Tree-sitter has no if node starting at this position`.
   The `else if (event == TM_LE)` is inside `#if defined(LUA_COMPAT_LT_LE)`, which
   `-DLUA_COMPAT_5_3` turns on; Tree-sitter cannot parse an `else` that follows an `#if` and puts
   it in an ERROR node (the same pattern as zlib `deflate.c:231`, limitation A in the project
   notes). instrument.py stops, as designed, instead of miscounting. `ltm.c` is compiled
   uninstrumented, so its decisions are not in the totals. Building without `-DLUA_COMPAT_5_3`
   would avoid it but would test a different program than `make linux` builds; not done.
3. **Directory mode stops at the first file instrument.py stops on.** `instrument.py src/ inst/`
   ended at `ltm.c` (file 23 of 33 in alphabetical order). The driver instruments file by file and
   keeps going, so one file does not block the rest.
4. **Tree-sitter syntax-error warnings in 28 of the 32 instrumented files.** instrument.py prints
   `Source file contains syntax errors — instrumentation may be incomplete` (Tree-sitter ERROR
   nodes, mostly from Lua's macros). Every decision Clang found was still paired with a node, and
   the instrumented suite behaves like the baseline, so the warning did not change the result
   here; which constructs cause it was not looked at.
5. **516 decisions come from macro expansions and are skipped** (282 of them in `lvm.c`, the VM
   loop's opcode macros; 48 each in `lapi.c` and `lgc.c`). They are counted and printed but not in
   the denominator (known limitation, docs/architecture.md). The 88.57 % is over the decisions
   written in the source text only.
6. **Two files have no decisions:** `lctype.c` (tables) and `lopcodes.c`; they are instrumented with
   0 ids.

## What I changed in C²oBra

- No change to `src/` (instrument.py, cov_runtime.c, run_tests.py, report.py, merge_reports.py,
  edges.py) and no change to the coverage logic.
- New `scripts/batch/lua_e2e.py`: the driver of the steps above (file-by-file instrumentation with global
  ids, build with Lua's flags, one coverage file per process, counter merge, reports).
  `unittests/test_lua_e2e.py` tests its two helpers (object list from the Makefile, counter merge).
  c2obra.sh was not used: its directory mode builds and runs every `.c` file as a separate program,
  and its runner (`run_tests.py`) feeds Sikraken XML inputs on stdin, while Lua is one program
  built from 33 files whose test inputs are Lua scripts on the command line.

## Per file

Sorted by coverage. `macro` = decisions skipped because they come from a macro.

| file | decisions | edges | covered | % | macro |
|---|---|---|---|---|---|
| lua.c | 68 | 145 | 37 | 25.5 | 0 |
| loadlib.c | 43 | 86 | 42 | 48.8 | 0 |
| lmem.c | 11 | 22 | 12 | 54.5 | 0 |
| loslib.c | 23 | 46 | 32 | 69.6 | 2 |
| lstate.c | 22 | 44 | 32 | 72.7 | 1 |
| lstring.c | 29 | 58 | 47 | 81.0 | 5 |
| lauxlib.c | 108 | 219 | 180 | 82.2 | 4 |
| lapi.c | 93 | 209 | 173 | 82.8 | 48 |
| ldblib.c | 45 | 90 | 76 | 84.4 | 0 |
| ldo.c | 86 | 179 | 156 | 87.2 | 15 |
| lobject.c | 47 | 126 | 114 | 90.5 | 12 |
| ltablib.c | 37 | 75 | 68 | 90.7 | 1 |
| ldebug.c | 104 | 253 | 230 | 90.9 | 3 |
| ltable.c | 85 | 187 | 171 | 91.4 | 6 |
| lundump.c | 28 | 62 | 57 | 91.9 | 11 |
| lgc.c | 137 | 307 | 285 | 92.8 | 48 |
| liolib.c | 50 | 103 | 96 | 93.2 | 0 |
| lcorolib.c | 14 | 30 | 28 | 93.3 | 0 |
| lvm.c | 152 | 336 | 318 | 94.6 | 282 |
| llex.c | 64 | 179 | 171 | 95.5 | 41 |
| lcode.c | 118 | 346 | 331 | 95.7 | 7 |
| lstrlib.c | 175 | 443 | 426 | 96.2 | 4 |
| lfunc.c | 20 | 40 | 39 | 97.5 | 3 |
| lparser.c | 132 | 324 | 316 | 97.5 | 16 |
| lmathlib.c | 27 | 56 | 55 | 98.2 | 0 |
| lutf8lib.c | 32 | 64 | 63 | 98.4 | 1 |
| lbaselib.c | 38 | 82 | 81 | 98.8 | 5 |
| ldump.c | 15 | 33 | 33 | 100.0 | 1 |
| lzio.c | 5 | 10 | 10 | 100.0 | 0 |
| linit.c | 1 | 2 | 2 | 100.0 | 0 |
| lctype.c | 0 | 0 | 0 | — | 0 |
| lopcodes.c | 0 | 0 | 0 | — | 0 |
| ltm.c | not instrumented | | | | |
| **total** | **1809** | **4156** | **3681** | **88.57** | **516** |

## Not done

- The full test suite (problem 1) and the internal-test-library build (`ltests`).
- `ltm.c` (problem 2) and the 516 macro decisions (problem 5).
- Whether all uncovered edges are reachable was not checked.
