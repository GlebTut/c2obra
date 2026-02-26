# C Testing Coverage Tool

A source-level branch coverage instrumentation tool for C programs.
The tool automatically instruments C source files to track which branches
are executed during testing, then reports coverage results.

## How It Works

1. **Instrument** — `src/instrument.py` parses a C source file using
   tree-sitter and injects coverage tracking calls around every branch
   (`if`, `while`, `for`, `do-while`)
2. **Compile & Run** — the instrumented file is compiled with
   `src/cov_runtime.c` and executed against test inputs
3. **Report** — branch coverage is calculated and printed as a summary

## Requirements

- Python 3.10+
- GCC
- gcc-multilib (for 32-bit compilation support used by Sikraken)
- python3-venv
- tree-sitter, tree-sitter-c (see `requirements.txt`)

## Setup

### 1. Install system dependencies

```bash
sudo apt install python3.12-venv gcc-multilib
```

> **Note:** `python3-venv` is required to create virtual environments on Debian/Ubuntu systems — it is not included by default. `gcc-multilib` is required for Sikraken's 32-bit (`-m32`) compilation mode.

### 2. Clone and set up the project

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
5. **Step 3** — runs all test cases via `src/run_tests.py` and outputs coverage results

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

### Run tests on all benchmarks
```bash
source venv/bin/activate
python3 src/run_tests.py
```

### Batch test
```bash
bash batch_test.sh
```

## Project Structure

```
C_Testing_Coverage_Tool/
├── src/
│   ├── instrument.py       # Core instrumentation logic
│   ├── run_tests.py        # Test runner and coverage reporter
│   ├── cov_runtime.c       # Runtime coverage tracking library
│   ├── cov_runtime.h       # Runtime header
│   └── verifier_stubs.c    # Stubs for SV-COMP verifier functions
├── tests/                  # C benchmark files (SV-COMP / custom)
│   ├── loop-simple/        # Loop-focused test cases
│   └── *.c                 # Conjunctive / linear / disjunctive benchmarks
├── output/                 # Instrumented files (generated, not tracked)
├── build/                  # Compiled test binaries (generated, not tracked)
├── docs/
│   └── testing-notes/      # Manual testing logs
├── run_pipeline.sh         # End-to-end pipeline script
├── batch_test.sh           # Batch test runner
└── requirements.txt
```

## Dependencies

| Package       | Version | Purpose                          |
| ------------- | ------- | -------------------------------- |
| tree-sitter   | 0.25.2  | C source parsing and AST walking |
| tree-sitter-c | 0.24.1  | C grammar for tree-sitter        |

## Sikraken (Required External Tool)

This tool uses **Sikraken** for symbolic execution and automatic test input generation.

- Download: https://zenodo.org/records/18062402
- Extract the zip to `~/sikraken/` so the script is at `~/sikraken/bin/sikraken.sh`
- Make all Sikraken scripts and binaries executable:

```bash
chmod +x ~/sikraken/bin/sikraken.sh
chmod -R +x ~/sikraken/bin/
chmod -R +x ~/sikraken/eclipse/
```

> **Important:** The Sikraken zip archive often does not preserve execute permissions. Running `chmod -R +x` on both `bin/` and `eclipse/` in one go avoids having to fix permissions incrementally for each binary (`call_parser.sh`, `sikraken_parser.exe`, the ECLiPSe engine, etc.).

## Troubleshooting

### `python3 -m venv venv` fails with "ensurepip is not available"

On Debian/Ubuntu, the `python3-venv` package is not installed by default:

```bash
sudo apt install python3.12-venv
```

---

### Sikraken fails with `Permission denied` on `.sh` scripts or `.exe` / `eclipse` binaries

The zip archive does not preserve execute permissions. Fix them all at once:

```bash
chmod -R +x ~/sikraken/bin/
chmod -R +x ~/sikraken/eclipse/
```

---

### Sikraken fails with `bits/wordsize.h: No such file or directory`

Sikraken compiles C files in 32-bit mode (`-m32`) and requires the 32-bit GCC support libraries:

```bash
sudo apt install gcc-multilib
```
