#!/usr/bin/env bash
set -e

# * Help
usage() {
  cat << 'EOF'
Usage:
  run_pipeline.sh <source.c> [options]
  run_pipeline.sh <source_dir/> [options]

Arguments:
  source.c          Path to a C source file to instrument, compile, and test.
  source_dir/       Path to a directory — all .c files are instrumented with
                    globally unique branch IDs and compiled as one binary.

Options:
  --cpu   N         CPU time limit per test run, in seconds.   Default: 30
  --memory N        Memory limit per test run, in MB.          Default: 512
  --wall  N         Wall-clock timeout per test run, in seconds.
                    Default: cpu + 5
  -h, --help        Show this help message and exit.

Output files (written to output/<base>/ or output/):
  <base>_inst.c                  Instrumented source (cover() calls injected)
  <base>_inst_branch_map.json    Branch metadata  (id, line, type)
  <base>_inst_coverage.json      Aggregated branch hit counts (all test runs)
  <base>_inst_test_inputs_log.json  Inputs used per test case
  <base>_inst_report.html        Interactive branch coverage report
  <base>_inst_source.html        VS Code-style syntax-highlighted source view
  summary_report.html            (directory mode) Overall summary across files

Coverage formula:
  coverage % = (true_branches_hit + false_branches_hit) / total_branches × 100

  Each branch construct (if, for, while, do, switch-case) produces 2 branches:
  one for the true path and one for the false path.

Examples:
  # Single file (no inputs):
  ./run_pipeline.sh examples/simple_if.c

  # Single file with __VERIFIER calls (Sikraken invoked automatically):
  ./run_pipeline.sh examples/nested_1.c

  # Directory mode:
  ./run_pipeline.sh examples/loop_suite/

  # Custom resource limits:
  ./run_pipeline.sh benchmarks/heavy.c --cpu 60 --memory 1024 --wall 70
EOF
  exit 0
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
fi

# * Validate arguments
if [ -z "$1" ]; then
    echo "❌ Usage: ./run_pipeline.sh <source.c|source_dir/> [--cpu N] [--memory N] [--wall N]"
    echo "   Run  ./run_pipeline.sh --help  for full usage."
    exit 1
fi
if [ ! -e "$1" ]; then
    echo "❌ Error: '$1' not found"
    exit 1
fi

# Resolve the project root (directory where this script lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Sikraken lives as a subfolder inside the project root.
# Can be overridden via env variable (e.g. in CI: SIKRAKEN_DIR=/tmp/sikraken-not-installed)
SIKRAKEN_DIR="${SIKRAKEN_DIR:-$(dirname "$SCRIPT_DIR")/sikraken}"
SIKRAKEN_OUT="$SIKRAKEN_DIR/sikraken_output"

# Helper: returns 0 if Sikraken is installed and usable, 1 otherwise
sikraken_available() {
  [ -d "$SIKRAKEN_DIR" ] && [ -f "$SIKRAKEN_DIR/bin/sikraken.sh" ]
}

# ─── SINGLE FILE MODE ─────────────────────────────────────────────────────────
if [ -f "$1" ]; then
    SRC="$1"
    BASENAME=$(basename "$SRC" .c)
    mkdir -p output/ build/

    # Auto-detect: does the file use __VERIFIER_nondet?
    if grep -q "__VERIFIER_nondet" "$SRC"; then
        echo "=== Detected: input-driven file ==="

        if ! sikraken_available; then
            echo "⚠️  Sikraken not found at $SIKRAKEN_DIR — skipping, running with no inputs"
            SUITE_DIR="-"
        else
            echo "=== Step 0: Run Sikraken ==="
            ABS_SRC="$(realpath "$SRC")"
            REL_SRC="$(realpath --relative-to="$SIKRAKEN_DIR" "$ABS_SRC")"
            cd "$SIKRAKEN_DIR"
            ./bin/sikraken.sh release budget[10] "$REL_SRC"
            cd "$SCRIPT_DIR"
            SUITE_DIR=$(find "$SIKRAKEN_OUT" -type d -name "test-suite" | grep "$BASENAME" | head -1)
            if [ -z "$SUITE_DIR" ]; then
                echo "⚠️  Warning: No Sikraken test suite found for '$BASENAME' — running with no inputs"
                SUITE_DIR="-"
            fi
            echo "✓ Sikraken done → $SUITE_DIR"
        fi
    else
        echo "=== Detected: no-input file ==="
        SUITE_DIR="-"
    fi

    # Step 1: Instrument
    echo "=== Step 1: Instrument ==="
    INST_OUT=$(python3 src/instrument.py "$SRC" output/"$BASENAME"_inst.c)
    echo "$INST_OUT"
    BRANCH_COUNTERS=$(echo "$INST_OUT" | grep '^BRANCH_COUNTERS=' | cut -d= -f2)

    # Step 2: Compile
    echo "=== Step 2: Compile ==="
    gcc output/"$BASENAME"_inst.c src/cov_runtime.c src/verifier_stubs.c \
        -o build/"$BASENAME"_test -I src/ \
        -DMAX_BRANCHES=${BRANCH_COUNTERS:-131072} \
        -w
    if [ ! -f "build/${BASENAME}_test" ]; then
        echo "❌ Compilation failed — binary not created"
        exit 1
    fi
    echo "✓ Binary built → build/${BASENAME}_test"

    # Step 3: Run Tests
    echo "=== Step 3: Run Tests ==="
    python3 src/run_tests.py \
        "build/${BASENAME}_test" \
        "${SUITE_DIR:-"-"}" \
        "output/${BASENAME}_inst_branch_map.json"

    # Save per-file inputs log
    if [ -f output/test_inputs_log.json ]; then
        mv output/test_inputs_log.json "output/${BASENAME}_inst_test_inputs_log.json"
    fi

    # Save coverage
    if [ -f output/coverage_report.json ]; then
        mv output/coverage_report.json "output/${BASENAME}_inst_coverage.json"
        echo "✓ Saved coverage → output/${BASENAME}_inst_coverage.json"
    else
        echo "⚠️ No coverage_report.json produced"
    fi

    # Step 4: Generate report
    python3 src/report.py \
    "output/${BASENAME}_inst_branch_map.json" \
    "output/${BASENAME}_inst_coverage.json" \
    --output      "output/${BASENAME}_inst_report.html" \
    --csv         "output/${BASENAME}_inst_report.csv" \
    --test-inputs "output/${BASENAME}_inst_test_inputs_log.json" \
    --no-summary || true

    echo "✅ Done → open output/${BASENAME}_inst_report.html"
    exit 0
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

        # Step 0: Run Sikraken if file uses __VERIFIER_nondet
        if grep -q "__VERIFIER_nondet" "$src_file"; then
            if ! sikraken_available; then
                echo "⚠️  Sikraken not found at $SIKRAKEN_DIR — skipping, running with no inputs"
                SUITE_DIR="-"
            else
                echo "=== Step 0: Run Sikraken for $base ==="
                ABS_SRC="$(realpath "$src_file")"
                REL_SRC="$(realpath --relative-to="$SIKRAKEN_DIR" "$ABS_SRC")"
                cd "$SIKRAKEN_DIR"
                ./bin/sikraken.sh release budget[10] "$REL_SRC" || true
                cd "$SCRIPT_DIR"
                SUITE_DIR=$(find "$SIKRAKEN_OUT" -type d -name "test-suite" | grep "$base" | head -1)
                if [ -z "$SUITE_DIR" ]; then
                    echo "⚠️ No Sikraken suite found for $base — running with no inputs"
                    SUITE_DIR="-"
                else
                    echo "✓ Sikraken done → $SUITE_DIR"
                fi
            fi
        else
            SUITE_DIR="-"
        fi

        # Step 2: Compile
        gcc "$inst" src/cov_runtime.c src/verifier_stubs.c \
            -o "build/${base}_test" -I src/ \
            -DMAX_BRANCHES=${GLOBAL_MAX} \
            -w 2>/dev/null || true

        if [ ! -f "build/${base}_test" ]; then
            echo "❌ Compilation failed for $base — skipping"
            continue
        fi
        echo "✓ Built build/${base}_test"

        # Step 3: Run tests
        python3 src/run_tests.py \
            "build/${base}_test" \
            "$SUITE_DIR" \
            "$OUT_DIR/${base}_inst_branch_map.json" || true

        # Save per-file inputs log
        if [ -f output/test_inputs_log.json ]; then
            cp output/test_inputs_log.json "$OUT_DIR/${base}_inst_test_inputs_log.json"
        fi

        # Save coverage
        if [ -f output/coverage_report.json ]; then
            mv output/coverage_report.json "$OUT_DIR/${base}_inst_coverage.json"
            echo "✓ Saved coverage → $OUT_DIR/${base}_inst_coverage.json"
        else
            echo "⚠️ No coverage_report.json for $base"
        fi

        # Step 5: Generate report
        python3 src/report.py \
            "$OUT_DIR/${base}_inst_branch_map.json" \
            "$OUT_DIR/${base}_inst_coverage.json" \
            --output      "$OUT_DIR/${base}_inst_report.html" \
            --csv         "$OUT_DIR/${base}_inst_report.csv" \
            --test-inputs "$OUT_DIR/${base}_inst_test_inputs_log.json" || true
    done

    echo ""
    echo "=== Summary Report ==="
    python3 src/merge_reports.py "$OUT_DIR"
    echo "✅ Done → open $OUT_DIR/summary_report.html"
    exit 0
fi

echo "❌ '$1' is neither a regular file nor a directory"
exit 1