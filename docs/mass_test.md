# Batch runs on Test-Comp tasks (`batch/mass_test.sh`)

Runs C²oBra, with Sikraken test suites, on the tasks of a `sample.csv`
(`category,yml_path,input_file,extension,data_model`, one row per Test-Comp task), one task
after another, unattended, and writes one result per task. Resumable after Ctrl-C or a killed
WSL.

```bash
# 20-task pilot (new run directory <runs-dir>/<YYYY-MM-DD>_pilot)
batch/mass_test.sh --name pilot --pilot 20
batch/mass_test.sh --name pilot --pilot 20 --dry-run      # only print the pilot tasks

# full sample, then resume after an interruption, then re-run some statuses
batch/mass_test.sh --name full
batch/mass_test.sh --run-dir ~/benchmarks/runs/2026-10-21_full
batch/mass_test.sh --run-dir ~/benchmarks/runs/2026-10-21_full --retry-status sikraken_timeout,run_crash
```

Defaults: `--sample ~/benchmarks/sample.csv`, `--sv-root <sample dir>/sv-benchmarks`,
`--runs-dir <sample dir>/runs`, `--sikraken-dir ../sikraken` (next to this repo).
`--limit N` takes the first N tasks in sample order, `--only-list FILE` the task ids or
`yml_path`s listed in FILE (one per line, `#` comments allowed). The driver never downloads
anything: a task whose input file is not on disk gets `input_missing`.

## One task

| Stage | What happens |
|---|---|
| prepare | Copy the input to `tasks/<id>/src/c2b__<id>.<ext>`, plus every `*.h` of the input's directory. If line 1 is a gcc line marker (`# <digit>`), every marker line (`# 12 "f.c" 2`) is replaced by an empty line, so line numbers stay the same (`cleaned_markers=1`). |
| sikraken | Only if the file contains `__VERIFIER_nondet`. `./bin/sikraken.sh release budget[10] -m32\|-m64 <copy>`, run from the Sikraken directory. Output goes to `sikraken_output/c2b__<id>/`; the driver deletes that directory before and after, and copies `test-suite/` into the task directory. |
| instrument, compile, run, report | `c2obra.sh <copy>` with `OUT_DIR=tasks/<id>/out`, `DATA_MODEL` from the .yml, `SIKRAKEN_SUITE` (the copied suite, or `-`), `LDLIBS=-lm`, `CFLAGS="-DLARGE_INT=1000000 -I<src dir>"`. Also runs after a Sikraken failure (with no inputs), to record whether C²oBra itself works on the file; the status stays the Sikraken one. |
| result | `edges_covered`, `edges_total`, `pct` from `merge_reports.compute_stats()`, which calls `edges.edge_coverage()`; nothing else computes coverage. |

**Task id**: the `.yml` path without `c/` and `.yml`, `/` → `__`, every other character outside
`[A-Za-z0-9_-]` → `_` (e.g. `c/ldv-linux-4.2-rc1/x.cil.out.yml` → `ldv-linux-4_2-rc1__x_cil_out`).
Test-Comp basenames repeat across directories, and Sikraken names its output directory after
the file name only, so the copy is named `c2b__<id>`. The ids of all 15,401 Cover-Branches tasks
are unique (checked by `tests/test_stages.py` with `C2OBRA_TASK_LIST`).

## Status values

The first failing stage decides the status (`stage` column: where it stopped).

| status | stage | detected by |
|---|---|---|
| `ok` | done | c2obra.sh exit 0, every test run `pass` |
| `partial` | done | finished, but some test runs ended on a signal or timed out (with at least one Sikraken test); `detail.run_signals` = {test: signal}, `detail.run_timeouts` |
| `no_tests` | done | nondet file, Sikraken exited normally but wrote no test (it was run once with no inputs; also when that run crashed or timed out) |
| `input_missing` | prepare | input file not on disk |
| `sikraken_parse` | sikraken | exit ≠ 0 and the log has `Sikraken ERROR from …call_parser.sh` (gcc -E, copy or parser failed); `detail.parser_error` = last non-Sikraken line before it |
| `sikraken_error` | sikraken | other exit ≠ 0 (ECLiPSe), or exit 0 without `test-suite/` (`sikraken.sh` turns exit 137 into 0) |
| `sikraken_timeout` | sikraken | driver timeout |
| `clang_error` | instrument | log `Clang reported N error(s)` / no Clang resource dir |
| `pairing_error` | instrument | log `could not be paired` |
| `instrument_error` | instrument | any other failure before Step 2 |
| `compile_error` | compile | exit ≠ 0 after `=== Step 2: Compile ===`; `detail.missing_symbols` = first 5 distinct `undefined reference` names, `detail.first_error` |
| `run_crash` | run | exit ≠ 0 after Step 3, no coverage JSON, or every test run crashed (not for a `no_tests` task) |
| `run_timeout` | run | driver timeout during Step 3, or every test run timed out (not for a `no_tests` task) |
| `tool_timeout` | instrument/compile/report | driver timeout outside Step 3 |
| `report_error` | report | branch map without `edges`, unreadable JSON |
| `driver_error` | – | c2obra.sh reported Done but exited ≠ 0 (should not happen) |

`run_tests.py` prints `[<test>] ended by SIGABRT (exit code -6)` for every run that ended on a
signal; the driver collects these. `cov_runtime.c` re-raises SIGSEGV/SIGABRT/SIGFPE, so those
are seen; SIGXCPU and SIGTERM end with `_exit(1)` and look like exit code 1.

The stage inside c2obra.sh is the last `=== Step N` marker in its log: under `set -e` a gcc
failure exits before `❌ Compilation failed` is printed, so that line cannot be relied on.
`detail.notes` lists known defects that make a task's numbers unreliable (none at present).

## Timeouts

| What | Default | Option |
|---|---|---|
| Sikraken (10 s CPU budget + parsing, which has no limit of its own) | 180 s wall | `--sikraken-timeout` |
| c2obra.sh, all four steps | 600 s wall | `--c2obra-timeout` |
| whole task | 900 s | `--task-timeout` |
| each test run (inside run_tests.py) | 30 s CPU, 35 s wall, 512 MB | not set by c2obra.sh (its `--cpu/--memory/--wall` options are documented but not parsed) |

Each child runs in its own process group (`start_new_session`). On timeout the group gets
SIGTERM, then SIGKILL after 5 s; this reaches ECLiPSe (under `prlimit` and `bash -lc`) and the
test binaries. Then the next task starts.

## Output

```
<runs-dir>/<YYYY-MM-DD>_<name>/
  tasks.txt        task ids of this run (fixed when the run is created)
  run.json         per invocation: argv, sample sha256, timeouts, c2obra commit + dirty flag,
                   Sikraken version.txt, gcc / clang / libclang / python versions
  results.csv      one row per finished task (rebuilt after every task)
  timing.csv       seconds per stage, one row per finished task (rebuilt after every task)
  summary.txt      status counts, category x status, times, 10 slowest, missing-symbol table
  tasks/<id>/      result.json, log.txt, out/ (branch map, coverage JSON, test inputs log,
                   report CSV), test-suite/ (tar.gz above 200 files), src/
  _incomplete/     interrupted attempts and --retry-status tasks, moved here, never deleted
```

Deleted after each task: the test binary, and `sikraken_output/c2b__<id>/`. For `ok` tasks also
the instrumented `.c`, the HTML reports and the input copy unless it was cleaned
(`detail.input_sha256` identifies the input). Failed tasks keep everything.

`results.csv` columns: `id,category,yml_path,input_file,extension,data_model,cleaned_markers,
status,stage,sikraken_tests,decisions,skipped_macro,skipped_outside_function,edges_covered,edges_total,pct,
seconds,log,detail,sikraken_exit,c2obra_exit,seconds_sikraken,seconds_c2obra,nondet` (`detail` is JSON).
`edges_total` is filled whenever a branch map exists; `edges_covered`/`pct` for `ok`, `partial`
and `no_tests`. The summary's edge total is the sum of the per-task `edge_coverage()` results
over `ok` and `partial` tasks that had at least one Sikraken test or no nondet call; it also
prints how many test runs ended on each signal.

`log.txt` has a `[HH:MM:SS.mmm +s]` timestamp (seconds since the task started) on each driver
stage and each c2obra.sh step line; `detail.step_seconds` = time per c2obra.sh step
(instrument, compile, run, report).

`timing.csv` columns: `id,category,extension,input_bytes,status,sikraken,parse,instrument,compile,run,
report,c2obra,total` (seconds). `parse` is the Tree-sitter parse plus the Clang scan, timed inside
instrument.py (`C2OBRA_TIMING_FILE`, kept in `detail.instrument_timing`); `instrument` is the rest of
c2obra.sh's instrument step (Python start-up, pairing, rewriting, writing the files). If instrument.py
stopped early, `parse` is empty and `instrument` is the whole step. `compile`, `run`, `report` are
c2obra.sh steps, `c2obra` its whole run, `total` the whole task. `input_bytes` is the size of the
input file in sv-benchmarks.

## Resume

A task is done when `tasks/<id>/result.json` exists and parses; it is written last, through a
temp file, `fsync` and `rename`. A task directory without it is an interrupted attempt: the
next run moves it to `_incomplete/` and runs the task again. `results.csv` and `summary.txt` are
rewritten whole (temp file + rename) from all `result.json` files, so they never hold half a
row. Ctrl-C or SIGTERM: the current process group is killed, no row is written for that task,
the outputs are rebuilt, exit code 130. A resumed run uses `tasks.txt`, not `--pilot` again.

## Pilot selection

Only tasks whose input is on disk. Cells = extension × data model; inside a cell tasks are
taken in `sha256("pilot:" + yml_path)` order, preferring categories not yet picked, N/4 per
cell, round-robin; short cells are filled by the others. If the sample has a `.i` with gcc line
markers or a file without `__VERIFIER_nondet` and the pick has none, one is swapped in. The
pilot must cover at least min(10, N) categories, otherwise the driver stops. The result depends
only on `sample.csv` and which inputs are on disk.

## Parallel runs (not implemented)

`-j N` would need, per task: its own cwd for `run_tests.py` (done: `OUT_DIR`), a unique
Sikraken output directory (done: `c2b__<id>`), no shared `build/` (done: `OUT_DIR`). There are
no ports; whether ECLiPSe writes shared temp files has not been checked. Limits: memory
(ECLiPSe reserves about 1–3 GB per process), CPU (`run_tests.py` already uses `cpu_count - 1`
threads), and the `seconds` columns would no longer be usable for timing claims.

## Tests

- `tests/test_stages.py`: ids, marker cleaning (line numbers kept; gcc -E d15 instruments after
  cleaning), classification (c2obra.sh logs are real: pairing error, link error, success),
  pilot, resume selection, CSV and summary.
- `tests/test_mass_test.py`: the driver on a fake benchmark tree with a fake Sikraken: every
  status that can be reached without the real Sikraken, two tasks with the same basename,
  group kill on timeout, resume, `--retry-status`, an interrupted task, Ctrl-C, pilot dry run.
- The pilot is the integration test with the real Sikraken and the real benchmarks.

## Known limitations (not tested on the real benchmarks yet)

- **Sikraken parser messages**: `sikraken_parse` detection uses the `ERROR from …call_parser.sh`
  line of `call_parser.sh`; the parser's own message format has not been captured yet.
- **`.i` from glibc ≥ 2.34 headers**: `__attribute__((__malloc__(f)))` is GCC-only; the Clang
  scan stops (`clang_error`). Seen with a local gcc 13 `.i`; not known for the Test-Comp `.i`.
- **Macros in `.i` files are counted**: after preprocessing, decisions from macros (e.g. the
  `if` inside glibc's `assert`) are plain text and get instrumented, while in a `.c` they are
  skipped (`tests/test_preprocessed_input.py`, d15: 3/8 for the `.i`, 1/2 for the `.c`). So
  `.c` and `.i` tasks are not counted the same way.
- **Line markers inside expressions** (gcc puts them inside `assert()` expansions) stop
  pairing; the driver cleans them when line 1 is a marker. A `.i` whose line 1 is not a marker
  is not cleaned.
- **`verifier_stubs.c`**: each nondet stub reads one token (strtoll / strtoull / strtod, Prolog
  `<num>Inf`/`<num>NaN` accepted); `__VERIFIER_nondet_memory` zero-fills and reads nothing,
  because Sikraken writes no input for it. Types Sikraken rejects (`pointer`, `pchar`, `int128`,
  `uint128`, `loff_t`, `sector_t`, `pthread_t`) have no stub → `compile_error` with
  `missing_symbols`. Prolog prints doubles with about 15 significant digits.
