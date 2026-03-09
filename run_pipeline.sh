#!/usr/bin/env bash
set -e

SRC="$1"
BASENAME=$(basename "$SRC" .c)
SIKRAKEN=~/sikraken/bin/sikraken.sh        
SIKRAKEN_OUT=~/sikraken/sikraken_output

# * Auto-detect: does the file use __VERIFIER_nondet?
if grep -q "__VERIFIER_nondet" "$SRC"; then
    echo "=== Detected: input-driven file ==="
    echo "=== Step 0: Run Sikraken ==="
    ABS_SRC="$(realpath "$SRC")"
    REL_SRC="$(realpath --relative-to="$HOME/sikraken" "$ABS_SRC")"
    cd ~/sikraken
    ./bin/sikraken.sh release budget[20] "$REL_SRC"
    cd ~/C_Testing_Coverage_Tool
    SUITE_DIR=$(find "$SIKRAKEN_OUT" -type d -name "test-suite" | grep "$BASENAME" | head -1)
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

# * Step 3: Run Tests
echo "=== Step 3: Run Tests ==="
python3 src/run_tests.py build/"$BASENAME"_test \
    "$SUITE_DIR" output/"$BASENAME"_inst_branch_map.json "${@:2}"