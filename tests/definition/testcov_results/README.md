# TestCov on the 15 definition programs

Rerun on 2026-10-26 of the TestCov run of 2026-10-21, same suite and same command.

## What was run

- TestCov: testcov-sikraken, `~/tools/testcov-sikraken`, branch `sikraken`, commit `26db1c6` (`26db1c60747b34647407d16f15dc9a675744fdfb`), venv `~/venvs/testcov` (Python 3.12.3). gcc 13.3.0.
- Programs: `tests/definition/d01_*.c` to `d15_*.c`.
- Suite: one empty test. `suite-noinput/metadata.xml` (`architecture` 64bit) and `suite-noinput/noinput.xml` (an empty `<testcase>`), zipped as `suite-noinput.zip`. The two XML files were written from the same text as on 2026-10-21 (the heredocs in that session); the zip itself is not kept here.
- Goal: TestCov's default (branch coverage); no `--goal`.
- Command, once per program, run with cwd `<run dir>/out` (all paths absolute, because the sikraken branch changes into the output folder):

  ```
  ~/venvs/testcov/bin/testcov --no-isolation -64 --test-suite <run dir>/suite-noinput.zip \
    --output <run dir>/out/<name> /home/glebt/c2obra/tests/definition/<name>.c
  ```

  The exact command of each program is in `<name>/cmd.txt` (`<run dir>` was a temporary folder).
- Source of the recipe: the Claude Code session of 2026-10-21 (12:56 to 12:59 UTC) that made the first run in `/tmp/testcov_def`, which no longer exists.

## Files

- `results.csv`: program, goals_total, goals_covered, status, coverage_printed. TestCov prints only the percentage and the number of goals; goals_covered = percentage x goals / 100.
- `exit_codes.txt`: TestCov exit code per program.
- `<name>/`: `cmd.txt`, `stdout.txt` (TestCov's console output), `testcov.log`, `results.json`, `noinput.info` (lcov file), `instrumented_<name>.c` (TestCov's instrumented copy). Not copied: `a.out`, `.gcno`, `harness.c`, `reduced-suite.zip` and the `.gcov` files (ignored by the repo's `.gitignore`).

## Comparison with the 2026-10-21 numbers

| program | 2026-10-21 | 2026-10-26 | |
|---|---|---|---|
| d01_if | 3/4 | 3/4 | OK |
| d02_else_if | 2/3 | 2/3 | OK |
| d03_while | 3/4 | 3/4 | OK |
| d04_for | 2/2 | 2/2 | OK |
| d05_do_while | 2/2 | 2/2 | OK |
| d06_while1 | 4/4 | 4/4 | OK |
| d07_for_infinite | 4/4 | 4/4 | OK |
| d08_ternary | 3/4 | 3/4 | OK |
| d09_switch_default | 3/3 | 3/3 | OK |
| d10_switch_no_default | 2/2 | 2/2 | OK |
| d11_switch_fallthrough | 2/3 | 2/3 | OK |
| d12_switch_stacked | 3/3 | 3/3 | OK |
| d13_switch_side_effect | 1/2 | 1/2 | OK |
| d14_logical_ops | 2/2 | 2/2 | OK |
| d15_macros | error ("else without a previous if") | error (`‘else’ without a previous ‘if’`, `instrumented_d15_macros.c:50`) | OK |
