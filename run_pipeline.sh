#!/bin/bash
set -e

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <source.c> <test-suite-dir>"
    exit 1
fi

SOURCE=$1
SUITE_DIR=$2
BASENAME=$(basename "$SOURCE" .c)
INST_FILE="output/${BASENAME}_inst.c"
MAP_FILE="output/${BASENAME}_inst_branch_map.json"
BINARY="build/${BASENAME}_test"

mkdir -p output build

echo "=== Step 1: Instrument ==="
python3 src/instrument.py "$SOURCE" "$INST_FILE"

echo ""
echo "=== Step 2: Compile ==="
gcc -I./src "$INST_FILE" src/cov_runtime.c src/verifier_stubs.c -o "$BINARY"
echo "✓ Compiled → $BINARY"

echo ""
echo "=== Step 3: Run Tests ==="
python3 src/run_tests.py "$BINARY" "$SUITE_DIR" "$MAP_FILE"

# Cleanup intermediate files
rm -f "$MAP_FILE"
rm -f test_input.txt