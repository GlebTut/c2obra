# C Testing Coverage Tool — Architecture

## Overview

The tool is a source-level branch coverage pipeline for C programs. It instruments C source
files at the AST level, compiles them with a lightweight runtime library, executes them
against test inputs, and generates interactive HTML/CSV coverage reports.

---

## Pipeline Architecture

### Single File Mode

```
┌─────────────────────────────────────────────────────────────────┐
│                        run_pipeline.sh                          │
└─────────────────────────────────────────────────────────────────┘
         │
         │  source.c
         ▼
┌─────────────────────┐
│    instrument.py    │  tree-sitter AST parse
│                     │  inject cover(true/false, id) calls
│                     │  assign unique branch IDs
└─────────────────────┘
         │
         ├──▶  output/<base>_inst.c              (instrumented source)
         └──▶  output/<base>_inst_branch_map.json (id → line, type metadata)

         │
         │  gcc + cov_runtime.c + verifier_stubs.c
         ▼
┌─────────────────────┐
│   GCC Compiler      │  -DMAX_BRANCHES=N
│                     │  links cov_runtime.c (signal handlers, JSON writer)
│                     │  links verifier_stubs.c (__VERIFIER_* stubs)
└─────────────────────┘
         │
         └──▶  build/<base>_test               (instrumented binary)

         │
         │  [optional] Sikraken symbolic execution
         ▼
┌─────────────────────┐
│    run_tests.py     │  ThreadPoolExecutor (cpu_count-1 workers)
│                     │  per-worker: isolated tempdir + COVERAGE_OUTPUT env
│                     │  two-stage kill: SIGTERM → 3s → SIGKILL
│                     │  classifies: pass / partial / timeout / crash
└─────────────────────┘
         │
         ├──▶  output/test_inputs_log.json      (inputs + status per test case)
         └──▶  output/coverage_report.json      (branch hit counts + summary)

         │
         ▼
┌─────────────────────┐
│     report.py       │  merges branch_map + coverage
│                     │  generates interactive HTML with dark mode
│                     │  generates VS Code-style source view
│                     │  generates CSV export
└─────────────────────┘
         │
         ├──▶  output/<base>_inst_report.html   (interactive coverage report)
         ├──▶  output/<base>_inst_report.csv    (CSV export)
         └──▶  output/<base>_inst_source.html   (syntax-highlighted source view)
```

---

### Directory Mode

```
┌─────────────────────────────────────────────────────────────────┐
│                        run_pipeline.sh                          │
└─────────────────────────────────────────────────────────────────┘
         │
         │  source_dir/*.c
         ▼
┌─────────────────────┐
│    instrument.py    │  instruments ALL .c files in one pass
│  (directory mode)   │  assigns GLOBALLY unique branch IDs across files
│                     │  outputs BRANCH_COUNTERS=N (total across all files)
└─────────────────────┘
         │
         └──▶  output/<dir>-output/<base>_inst.c            (per file)
         └──▶  output/<dir>-output/<base>_inst_branch_map.json (per file)

         │  for each .c file:
         ▼
    [gcc → run_tests.py → report.py]   (same as single file mode)
         │
         └──▶  output/<dir>-output/<base>_inst_report.html  (per file)

         │
         ▼
┌─────────────────────┐
│  merge_reports.py   │  aggregates all per-file coverage JSONs
│                     │  builds overall summary table
└─────────────────────┘
         │
         └──▶  output/<dir>-output/summary_report.html      (overall summary)
```

---

## Component Descriptions

### `src/instrument.py`
- Parses C source using **tree-sitter** AST
- Injects `cover(side, branch_id)` calls at every `if`, `for`, `while`, `do-while`, and `switch` branch point
- Strips conflicting `__VERIFIER_*` definitions and `typedef size_t`
- Outputs instrumented `.c` and `branch_map.json` with `id`, `line`, `type`, `source_file`
- In directory mode: assigns globally unique IDs across all files in one pass

### `src/cov_runtime.c` / `src/cov_runtime.h`
- Global `uint64_t branch_counters[MAX_BRANCHES]` array
- `cover(side, id)` macro increments `branch_counters[id*2 + side]`
- `dump_coverage()` writes hit counts to `$COVERAGE_OUTPUT` as JSON
- `__attribute__((destructor))` fires on normal `exit()`
- `signal_handler_soft` (SIGXCPU, SIGTERM): dump + `_exit(1)`
- `signal_handler_crash` (SIGSEGV, SIGABRT, SIGFPE): dump + re-raise signal
- Double-write guard via `coverage_written` flag

### `src/verifier_stubs.c` / `src/verifier_stubs.h`
- Provides `__VERIFIER_nondet_*()` stubs returning `0` for all types
- Provides `__VERIFIER_assume()`, `__VERIFIER_error()`, `reach_error()`
- `__attribute__((weak))` on `__VERIFIER_assert` to avoid linker conflicts

### `src/run_tests.py`
- Discovers `test_input-*.xml` files in Sikraken test suite directory
- Runs binary with `ThreadPoolExecutor(max_workers=cpu_count-1)`
- Each worker: isolated `tempfile.mkdtemp()` + unique `COVERAGE_OUTPUT` path
- Resource limits: `setrlimit(RLIMIT_CPU)` per worker
- Two-stage kill on timeout: `SIGTERM` → 3s grace → `SIGKILL`
- Classifies each run: `pass` / `partial` / `timeout` / `crash`
- Merges all per-worker coverage JSONs into aggregated `coverage_report.json`

### `src/report.py`
- Merges `branch_map.json` + `coverage_report.json`
- Generates interactive HTML report with dark/light mode, sorting, filtering
- Generates VS Code-style syntax-highlighted source view with branch colour-coding
- Generates CSV export
- CLI: `--output`, `--csv`, `--test-inputs` for per-file path control

### `src/merge_reports.py`
- Reads all `*_inst_coverage.json` files in a directory
- Builds aggregated summary table with per-file coverage percentages
- Links to each file's individual `_report.html` and `_source.html`
- Outputs `summary_report.html`

---

## Runtime Data Flow

```
cover(side, id)                     ← called at every branch point during execution
      │
      ▼
branch_counters[id*2 + side]++      ← in-memory, ultra-fast (array increment)
      │
      ▼  on exit / signal
dump_coverage()
      │
      ▼
$COVERAGE_OUTPUT/coverage.json      ← {"branches": [{"id":1,"true":3,"false":0}, ...]}
      │
      ▼
run_tests.py: merge_coverage()      ← aggregates across all test cases
      │
      ▼
output/coverage_report.json         ← final aggregated result
```

---

## Signal Handling

```
Normal exit()          →  __attribute__((destructor))  →  dump_coverage()
SIGXCPU (CPU limit)    →  signal_handler_soft           →  dump_coverage() + _exit(1)
SIGTERM (soft kill)    →  signal_handler_soft           →  dump_coverage() + _exit(1)
SIGSEGV (segfault)     →  signal_handler_crash          →  dump_coverage() + re-raise
SIGABRT (abort)        →  signal_handler_crash          →  dump_coverage() + re-raise
SIGFPE  (div by zero)  →  signal_handler_crash          →  dump_coverage() + re-raise
SIGKILL (force kill)   →  (cannot be caught)            →  coverage lost
```

The two-stage kill in `run_tests.py` (`SIGTERM` → 3s → `SIGKILL`) ensures `SIGKILL`
is only sent if the process does not respond to `SIGTERM`, minimising coverage loss
on timeout.

---

## Output File Map

```
output/
├── <base>_inst.c                      Instrumented source
├── <base>_inst_branch_map.json        Branch metadata (id, line, type, source_file)
├── <base>_inst_coverage.json          Aggregated branch hit counts + summary
├── <base>_inst_test_inputs_log.json   Test cases with inputs and run status
├── <base>_inst_report.html            Interactive HTML coverage report
├── <base>_inst_report.csv             CSV export of branch coverage data
├── <base>_inst_report_source.html     VS Code-style syntax-highlighted source view
│
└── <dir>-output/                      (directory mode only)
    ├── <base>_inst_*                  (same structure per file)
    └── summary_report.html            Overall summary across all files
```

---

## Dependencies

| Component | Dependency | Purpose |
|---|---|---|
| `instrument.py` | `tree-sitter`, `tree-sitter-c` | AST parsing of C source |
| `cov_runtime.c` | `gcc`, `libc` | Signal handling, JSON output |
| `run_tests.py` | Python 3.8+, stdlib only | Test execution, coverage merging |
| `report.py` | Python 3.8+, stdlib only | HTML/CSV report generation |
| `run_pipeline.sh` | `bash`, `gcc`, `realpath` | Pipeline orchestration |
| Sikraken | External tool | Symbolic execution, test input generation |

---

## References

- Tree-sitter Python bindings: https://github.com/tree-sitter/py-tree-sitter
- GCC, the GNU Compiler Collection: https://gcc.gnu.org
- Sikraken symbolic execution tool: https://zenodo.org/records/18062402
- SV-Benchmarks Test-COMP suite: https://gitlab.com/sosy-lab/benchmarking/sv-benchmarks
