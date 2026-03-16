#!/usr/bin/env bash
set -e

# * Validate arguments
if [ -z "$1" ]; then
    echo "❌ Usage: ./run_pipeline.sh <source.c|source_dir/> [--cpu N] [--memory N] [--wall N]"
    exit 1
fi
if [ ! -e "$1" ]; then
    echo "❌ Error: '$1' not found"
    exit 1
fi

# ─── DIRECTORY MODE ───────────────────────────────────────────────────────────
if [ -d "$1" ]; then
    SRC="$1"
    DIRNAME=$(basename "$SRC")
    OUT_DIR="output/${DIRNAME}-output"
    mkdir -p "$OUT_DIR" build/

    echo "=== Directory mode: $SRC ==="
    echo "=== Step 1: Instrument ==="

    INST_OUTPUT=$(python3 src/instrument.py "$SRC" "$OUT_DIR")
    echo "$INST_OUTPUT"
    GLOBAL_MAX=$(echo "$INST_OUTPUT" | grep '^BRANCH_COUNTERS=' | tail -1 | cut -d= -f2)
    echo "Global MAX_BRANCHES: ${GLOBAL_MAX}"

    for src_file in "$SRC"/*.c; do
        [ -f "$src_file" ] || continue
        base=$(basename "$src_file" .c)
        inst="$OUT_DIR/${base}_inst.c"
        [ -f "$inst" ] || { echo "⚠️ No instrumented file for $base — skipping"; continue; }

        echo ""
        echo "--- Processing $base ---"

        gcc "$inst" src/cov_runtime.c src/verifier_stubs.c \
            -o "build/${base}_test" -I src/ -DMAX_BRANCHES=${GLOBAL_MAX}

        if [ ! -f "build/${base}_test" ]; then
            echo "❌ Compilation failed for $base — skipping"
            continue
        fi
        echo "✓ Built build/${base}_test"

        python3 src/run_tests.py "build/${base}_test" \
            - "$OUT_DIR/${base}_inst_branch_map.json" "${@:2}"

        if [ -f coverage_report.json ]; then
            mv coverage_report.json "$OUT_DIR/${base}_inst_coverage.json"
            echo "✓ Saved coverage → $OUT_DIR/${base}_inst_coverage.json"
        fi

        python3 src/report.py \
            "$OUT_DIR/${base}_inst_branch_map.json" \
            "$OUT_DIR/${base}_inst_coverage.json"
    done

    echo ""
    echo "=== Summary Report ==="
    python3 src/merge_reports.py "$OUT_DIR"
    echo "✅ Done → open $OUT_DIR/summary_report.html"
    exit 0
fi

# ─── SINGLE FILE MODE ─────────────────────────────────────────────────────────
SRC="$1"
BASENAME=$(basename "$SRC" .c)
SIKRAKEN_OUT=~/sikraken/sikraken_output
mkdir -p output/ build/

# Auto-detect: does the file use __VERIFIER_nondet?
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

# Step 1: Instrument + capture BRANCH_COUNTERS
echo "=== Step 1: Instrument ==="
INST_OUT=$(python3 src/instrument.py "$SRC" output/"$BASENAME"_inst.c)
echo "$INST_OUT"
BRANCH_COUNTERS=$(echo "$INST_OUT" | grep '^BRANCH_COUNTERS=' | cut -d= -f2)

# Step 2: Compile
echo "=== Step 2: Compile ==="
gcc output/"$BASENAME"_inst.c src/cov_runtime.c src/verifier_stubs.c \
    -o build/"$BASENAME"_test -I src/ -DMAX_BRANCHES=${BRANCH_COUNTERS:-131072}
if [ ! -f "build/${BASENAME}_test" ]; then
    echo "❌ Compilation failed — binary not created"
    exit 1
fi
echo "✓ Binary built → build/${BASENAME}_test"

# Step 3: Run Tests
echo "=== Step 3: Run Tests ==="
python3 src/run_tests.py build/"$BASENAME"_test \
    "$SUITE_DIR" output/"$BASENAME"_inst_branch_map.json "${@:2}"

# Step 4: Generate report
echo "=== Step 4: Report ==="
if [ -f coverage_report.json ]; then
    mv coverage_report.json output/"$BASENAME"_inst_coverage.json
fi
python3 src/report.py \
    output/${BASENAME}_inst_branch_map.json \
    output/${BASENAME}_inst_coverage.json
