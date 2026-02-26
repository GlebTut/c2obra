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
- tree-sitter, tree-sitter-c (see `requirements.txt`)

## Setup

```bash
git clone https://github.com/GlebTut/C_Testing_Coverage_Tool
cd C_Testing_Coverage_Tool

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Run the full pipeline on a single file
```bash
bash run_pipeline.sh tests/benchmark01_conjunctive.c
```

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
├── parsers_testing/        # Exploratory parser benchmarking scripts
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
- Extract the zip and make the script executable:

```bash
chmod +x bin/sikraken.sh
```