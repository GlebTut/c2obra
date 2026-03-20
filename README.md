# C Testing Coverage Tool

A source-level branch coverage instrumentation tool for C programs.
The tool automatically instruments C source files to track which branches
are executed during testing, then reports coverage results as interactive
HTML/CSV reports with VS Code-style source view.

## How It Works

1. **Instrument** — `src/instrument.py` parses a C source file using tree-sitter and injects `cover()` macros around every branch (`if`, `while`, `for`, `do-while`, `switch`)
2. **Compile & Run** — the instrumented file is compiled with `src/cov_runtime.c` and executed against Sikraken-generated test inputs
3. **Report** — branch coverage is calculated per edge (true/false) and output as JSON + interactive HTML/CSV with source-code view

## Requirements

- Python 3.10+
- GCC
- gcc-multilib (for 32-bit compilation support used by Sikraken)
- python3-venv
- tree-sitter, tree-sitter-c (see `requirements.txt`)

## Setup

### Option A — Quick install (recommended)

```bash
git clone https://github.com/GlebTut/C_Testing_Coverage_Tool.git
cd C_Testing_Coverage_Tool
chmod +x install.sh
bash install.sh
```

### Option B — Manual setup

#### 1. Install system dependencies

```bash
sudo apt install python3.12-venv gcc-multilib
```

#### 2. Clone and set up the project

```bash
git clone https://github.com/GlebTut/C_Testing_Coverage_Tool.git
cd C_Testing_Coverage_Tool
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Run the full pipeline on a single file

```bash
bash run_pipeline.sh filePATH/fileNAME
```

The pipeline runs these steps automatically:

1. **Auto-detects** if the file uses `__VERIFIER_nondet_*` inputs
2. **Step 0** *(input-driven files only)* — runs Sikraken with a 20s budget to generate a test suite XML
3. **Step 1** — instruments the C file with `cover()` macros via `src/instrument.py`
4. **Step 2** — compiles the instrumented file with `gcc` + `cov_runtime.c` + `verifier_stubs.c`
5. **Step 3** — runs all test cases via `src/run_tests.py` (parallel execution) and outputs coverage results

**Example output:**

```
=== Detected: input-driven file ===
=== Step 0: Run Sikraken ===
✓ Sikraken done → ~/sikraken/sikraken_output/benchmark01_conjunctive/test-suite
=== Step 1: Instrument ===
=== Step 2: Compile ===
=== Step 3: Run Tests ===
```

> **Note:** Sikraken must be installed at `~/sikraken/` — see the Sikraken section below.

### Run the full pipeline on a directory

```bash
bash run_pipeline.sh path/to/directory/
```

Recursively instruments all `.c` files, assigns globally unique branch IDs across all files, compiles and runs each benchmark, then generates a summary report at `output/summary_report.html`.

### Run tests on all benchmarks

```bash
source venv/bin/activate
python3 src/run_tests.py
```

### Batch test

```bash
bash batch_test.sh
```

### Generate HTML/CSV report manually

```bash
source venv/bin/activate
python3 src/report.py output/benchmark_inst_branch_map.json output/benchmark_inst_coverage.json
```

This generates:
- `output/benchmark_inst_report.html` — interactive coverage report with dark mode, sorting, filtering
- `output/benchmark_inst_report.csv` — CSV export
- `output/benchmark_inst_source.html` — VS Code-style source view with branch highlighting

### Generate summary report across multiple benchmarks

```bash
source venv/bin/activate
python3 src/merge_reports.py output/
```

## Coverage Model

The tool uses an **edge-based branch coverage model** consistent with gcov:

```
coverage % = (true_edges_hit + false_edges_hit) / (total_branches × 2) × 100
```

Each branch (`if`/`while`/`for`/`switch` case) contributes **2 edges** to the total.
This correctly handles cases where a loop condition may be entered but never exit false.

## Project Structure

```
C_Testing_Coverage_Tool/
├── src/
│   ├── instrument.py       # Core instrumentation logic (tree-sitter AST)
│   ├── run_tests.py        # Parallel test runner and coverage reporter
│   ├── report.py           # HTML/CSV/source-view report generator
│   ├── merge_reports.py    # Summary report across multiple benchmarks
│   ├── cov_runtime.c       # Runtime coverage tracking library (SIGXCPU handler)
│   ├── cov_runtime.h       # Runtime header (cover() macro, MAX_BRANCHES guard)
│   └── verifier_stubs.c    # Stubs for SV-COMP verifier functions
├── tests/                  # C benchmark files (SV-COMP / custom)
│   ├── loop-simple/        # Loop-focused test cases
│   └── *.c                 # Conjunctive / linear / disjunctive benchmarks
├── output/                 # Instrumented files and reports (generated, not tracked)
├── build/                  # Compiled test binaries (generated, not tracked)
├── docs/
│   └── testing-notes/      # Manual testing logs
├── run_pipeline.sh         # End-to-end pipeline script
├── batch_test.sh           # Batch test runner
├── install.sh              # One-command installer
└── requirements.txt
```

## Dependencies

| Package       | Version | Purpose                          |
| ------------- | ------- | -------------------------------- |
| tree-sitter   | 0.25.2  | C source parsing and AST walking |
| tree-sitter-c | 0.24.1  | C grammar for tree-sitter        |

## Benchmark Results (Iteration 2)

| Benchmark Set            | This Tool | TestCoCa | testcov |
|--------------------------|-----------|----------|---------|
| Custom benchmarks (12)   | 84.9%     | 79.8%    | 76.3%   |
| SV-COMP benchmarks (145) | 58.1%     | 50.4%    | 47.7%   |
| All benchmarks (157)     | 60.2%     | 53.3%    | 51.0%   |

- **145/145** SV-COMP benchmarks compiled and ran successfully
- **2,230** branches instrumented across the benchmark suite
- **25–29%** runtime overhead (well within the <30% target)
- **3.91s** instrumentation time on a 5.7 MB, 171,590-line file

## Sikraken (Required External Tool)

This tool uses **Sikraken** for symbolic execution and automatic test input generation.

- Download: [https://zenodo.org/records/18062402](https://zenodo.org/records/18062402)
- Extract the zip to `~/sikraken/` so the script is at `~/sikraken/bin/sikraken.sh`
- Make all Sikraken scripts and binaries executable:

```bash
chmod +x ~/sikraken/bin/sikraken.sh
chmod -R +x ~/sikraken/bin/
chmod -R +x ~/sikraken/eclipse/
```

> **Important:** The Sikraken zip archive often does not preserve execute permissions. Running `chmod -R +x` on both `bin/` and `eclipse/` avoids fixing permissions incrementally for each binary.

## Troubleshooting

### `python3 -m venv venv` fails with "ensurepip is not available"

```bash
sudo apt install python3.12-venv
```

---

### Sikraken fails with `Permission denied` on `.sh` or `eclipse` binaries

```bash
chmod -R +x ~/sikraken/bin/
chmod -R +x ~/sikraken/eclipse/
```

---

### Sikraken fails with `bits/wordsize.h: No such file or directory`

```bash
sudo apt install gcc-multilib
```

---

### Coverage report shows 0% on a benchmark that ran successfully

This usually means the binary was killed by SIGKILL before coverage was flushed.
Ensure you are using `run_pipeline.sh` (which sets resource limits correctly) rather than running the binary directly.
