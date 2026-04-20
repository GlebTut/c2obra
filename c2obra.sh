#!/usr/bin/env bash
set -e
if [ -f "$(dirname "${BASH_SOURCE[0]}")/venv/bin/activate" ]; then
    source "$(dirname "${BASH_SOURCE[0]}")/venv/bin/activate"
fi


# * Help
usage() {
  cat << 'EOF'
Usage:
  c2obra.sh <source.c> [options]
  c2obra.sh <source_dir/> [options]


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
  <base>_inst.c                     Instrumented source
  <base>_inst_branch_map.json       Branch metadata
  <base>_inst_coverage.json         Aggregated branch hit counts
  <base>_inst_test_inputs_log.json  Inputs used per test case
  <base>_inst_report.html           Interactive branch coverage report
  <base>_inst_source.html           Syntax-highlighted source view
  summary_report.html               (directory mode) Overall summary across files


Coverage formula:
  coverage % = (true_branches_hit + false_branches_hit) / total_branches x 100
EOF
  exit 0
}


if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
fi


if [ -z "$1" ]; then
    echo "❌ Usage: ./c2obra.sh <source.c|source_dir/> [--cpu N] [--memory N] [--wall N]"
    exit 1
fi
if [ ! -e "$1" ]; then
    echo "❌ Error: '$1' not found"
    exit 1
fi


# Resolve project root and Sikraken location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIKRAKEN_DIR="${SIKRAKEN_DIR:-$(dirname "$SCRIPT_DIR")/sikraken}"
SIKRAKEN_OUT="$SIKRAKEN_DIR/sikraken_output"


# Returns 0 if Sikraken is installed and usable
sikraken_available() {
  [ -d "$SIKRAKEN_DIR" ] && [ -f "$SIKRAKEN_DIR/bin/sikraken.sh" ]
}


# ─── SINGLE FILE MODE ─────────────────────────────────────────────────────────
if [ -f "$1" ]; then
    SRC="$1"
    BASENAME=$(basename "$SRC" .c)
    mkdir -p output/ build/

    # Auto-detect: does the file use __VERIFIER_nondet inputs?
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

    # Step 1: Instrument source
    echo "=== Step 1: Instrument ==="
    INST_OUT=$(/home/glebt/c2obra/venv/bin/python3 src/instrument.py "$SRC" output/"$BASENAME"_inst.c)
    echo "$INST_OUT"
    BRANCH_COUNTERS=$(echo "$INST_OUT" | grep '^BRANCH_COUNTERS=' | cut -d= -f2)

    # Step 2: Compile instrumented source + runtime
    echo "=== Step 2: Compile ==="
    gcc output/"$BASENAME"_inst.c src/cov_runtime.c src/verifier_stubs.c \
        -o build/"$BASENAME"_test -I src/ \
        -DMAX_BRANCHES=${BRANCH_COUNTERS:-131072} \
        -w
    [ -f "build/${BASENAME}_test" ] || { echo "❌ Compilation failed"; exit 1; }
    echo "✓ Binary built → build/${BASENAME}_test"

    # Step 3: Run tests and collect coverage
    echo "=== Step 3: Run Tests ==="
    /home/glebt/c2obra/venv/bin/python3 src/run_tests.py \
        "build/${BASENAME}_test" \
        "${SUITE_DIR:-"-"}" \
        "output/${BASENAME}_inst_branch_map.json"

    if [ -f output/test_inputs_log.json ]; then
        mv output/test_inputs_log.json "output/${BASENAME}_inst_test_inputs_log.json"
    fi

    # Keep coverage_report.json in place for CI index aggregation (copy, not move)
    if [ -f output/coverage_report.json ]; then
        cp output/coverage_report.json "output/${BASENAME}_inst_coverage.json"
        echo "✓ Saved coverage → output/${BASENAME}_inst_coverage.json"
    else
        echo "⚠️ No coverage_report.json produced"
    fi

    # Step 4: Generate HTML report
    /home/glebt/c2obra/venv/bin/python3 src/report.py \
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

    # Step 1: Instrument all .c files with globally unique branch IDs
    echo "=== Step 1: Instrument ==="
    INST_OUTPUT=$(/home/glebt/c2obra/venv/bin/python3 src/instrument.py "$SRC" "$OUT_DIR")
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

        # Step 0 (per file): Run Sikraken if file uses __VERIFIER_nondet
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

        # Step 2: Compile (all files share GLOBAL_MAX branch counter size)
        gcc "$inst" src/cov_runtime.c src/verifier_stubs.c \
            -o "build/${base}_test" -I src/ \
            -DMAX_BRANCHES=${GLOBAL_MAX} \
            -w 2>/dev/null || true

        [ -f "build/${base}_test" ] || { echo "❌ Compilation failed for $base — skipping"; continue; }
        echo "✓ Built build/${base}_test"

        # Step 3: Run tests
        /home/glebt/c2obra/venv/bin/python3 src/run_tests.py \
            "build/${base}_test" \
            "$SUITE_DIR" \
            "$OUT_DIR/${base}_inst_branch_map.json" || true

        if [ -f output/test_inputs_log.json ]; then
            cp output/test_inputs_log.json "$OUT_DIR/${base}_inst_test_inputs_log.json"
        fi

        if [ -f output/coverage_report.json ]; then
            mv output/coverage_report.json "$OUT_DIR/${base}_inst_coverage.json"
            echo "✓ Saved coverage → $OUT_DIR/${base}_inst_coverage.json"
        else
            echo "⚠️ No coverage_report.json for $base"
        fi

        # Step 4: Generate per-file HTML report
        /home/glebt/c2obra/venv/bin/python3 src/report.py \
            "$OUT_DIR/${base}_inst_branch_map.json" \
            "$OUT_DIR/${base}_inst_coverage.json" \
            --output      "$OUT_DIR/${base}_inst_report.html" \
            --csv         "$OUT_DIR/${base}_inst_report.csv" \
            --test-inputs "$OUT_DIR/${base}_inst_test_inputs_log.json" || true
    done

    # Step 5: Generate summary report across all files
    echo ""
    echo "=== Summary Report ==="
    /home/glebt/c2obra/venv/bin/python3 src/merge_reports.py "$OUT_DIR"

    # Step 6: Write aggregate coverage_report.json for CI index page
    /home/glebt/c2obra/venv/bin/python3 - "$OUT_DIR" <<'PYEOF'
import os, json, glob, sys
out_dir = sys.argv[1]  # passed explicitly — no glob guessing
jsons = glob.glob(f"{out_dir}/*_inst_coverage.json")
total_e = covered_e = 0
for j in jsons:
    try:
        with open(j) as f:
            d = json.load(f)
        total_e   += d["summary"].get("total_branches_count", 0)
        covered_e += d["summary"].get("covered_branches", 0)
    except Exception as e:
        print(f"⚠️  Skipping {j}: {e}")
pct = round(covered_e / total_e * 100, 1) if total_e else 0
out_path = os.path.join(out_dir, "coverage_report.json")
with open(out_path, "w") as f:
    json.dump({
        "summary": {
            "total_branches_count": total_e,
            "covered_branches":     covered_e,
            "branch_coverage_pct":  pct,
            "coverage_pct":         pct
        }
    }, f, indent=2)
print(f"✓ Aggregate coverage_report.json → {covered_e}/{total_e} ({pct}%)")
PYEOF

    echo "✅ Done → open $OUT_DIR/summary_report.html"
    exit 0
fi


echo "❌ '$1' is neither a regular file nor a directory"
exit 1