# C Testing Coverage Tool

A source-level branch coverage instrumentation tool for C programs.
The tool automatically instruments C source files to track which branches
are executed during testing, then reports coverage results.

## How It Works

1. **Instrument** — `src/instrument.py` parses a C source file using
   pycparser and injects coverage tracking calls around every branch
   (`if`, `while`, `for`, `do-while`, `switch`)
2. **Compile & Run** — the instrumented file is compiled with
   `src/cov_runtime.c` and executed against test inputs
3. **Report** — branch coverage is calculated and printed as a summary

## Requirements

- Python 3.10+
- GCC
- pycparser, tree-sitter, tree-sitter-c (see `requirements.txt`)

## Setup

```bash
git clone <repo-url>
cd C_Testing_Coverage_Tool

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
