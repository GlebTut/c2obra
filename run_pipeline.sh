#!/usr/bin/env bash
set -e

# * Validate arguments
if [ -z "$1" ]; then
    echo "❌ Usage: ./run_pipeline.sh <source.c> [--cpu N] [--memory N] [--wall N]"
    exit 1
fi
if [ ! -f "$1" ]; then
    echo "❌ Error: Source file '$1' not found"
    exit 1
fi

SRC="$1"
BASENAME=$(basename "$SRC" .c)
SIKRAKEN_OUT=~/sikraken/sikraken_output

# * Ensure output dirs exist
mkdir -p output/ build/

# * Auto-detect: does the file use __VERIFIER_nondet?
if grep -q "__VERIFIER_nondet" "$SRC"; then
    echo "=== Detected: input-driven file ==="
    echo "=== Step 0: Run Sikraken ==="
    ABS_SRC="$(realpath "$SRC")"
    REL_SRC="$(realpath --relative-to="$HOME/sikraken" "$ABS_SRC")"
    cd ~/sikraken
    ./bin/sikraken.sh release budget[10] "$REL_SRC"
    cd ~/C_Testing_Coverage_Tool
    SUITE_DIR=$(find "$SIKRAKEN_OUT" -type d -name "test-suite" | grep "$BASENAME" | head -1)
    if [ -z "$SUITE_DIR" ]; then
        echo "⚠️  Warning: No Sikraken test suite found for '$BASENAME' — running with no inputs"
        SUITE_DIR="-"
    fi
    echo "✓ Sikraken done → $SUITE_DIR"
else
    echo "=== Detected: no-input file ==="
    SUITE_DIR="-"
fi

# * Step 1: Instrument
echo "=== Step 1: Instrument ==="
python3 src/instrument.py "$SRC" output/"$BASENAME"_inst.c

# * Step 2: Compile
echo "=== Step 2: Compile ==="
gcc output/"$BASENAME"_inst.c src/cov_runtime.c src/verifier_stubs.c \
    -o build/"$BASENAME"_test -I src/
if [ ! -f "build/${BASENAME}_test" ]; then
    echo "❌ Compilation failed — binary not created"
    exit 1
fi
echo "✓ Binary built → build/${BASENAME}_test"

# * Step 3: Run Tests
echo "=== Step 3: Run Tests ==="
python3 src/run_tests.py build/"$BASENAME"_test \
    "$SUITE_DIR" output/"$BASENAME"_inst_branch_map.json "${@:2}"

# * Step 4: Generate report
echo "=== Step 4: Report ==="
python3 src/report.py \
  output/${BASENAME}_inst_branch_map.json \
  coverage_report.json