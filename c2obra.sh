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
                    globally unique branch IDs; each .c file directly in the
                    directory is built and run as its own binary.


Options:
  --cpu   N         CPU time limit per test run, in seconds.   Default: 30
  --memory N        Memory limit per test run, in MB.          Default: 512
  --wall  N         Wall-clock timeout per test run, in seconds.
                    Default: cpu + 5
  -h, --help        Show this help message and exit.


Environment (single-file mode; unset = the behaviour described above):
  CFLAGS            Flags for the Clang scan and gcc. Default: -DLARGE_INT=1000000
  DATA_MODEL        ILP32 (or -m32) / LP64 (or -m64): passed to the Clang scan, gcc and
                    Sikraken. Unset: no flag (gcc builds 64-bit, Sikraken defaults to -m32).
  OUT_DIR           Write every output (and the binary) here instead of output/ and build/.
  SIKRAKEN_SUITE    Test-suite directory to use, or "-" for none; Sikraken is not run.
  LDLIBS            Extra libraries for the gcc link step, e.g. "-lm".
  SIKRAKEN_DIR      Sikraken install. Default: ../sikraken next to this script.


Output files (written to output/<base>/ or output/):
  <base>_inst.c                     Instrumented source
  <base>_inst_branch_map.json       Branch metadata
  <base>_inst_coverage.json         Aggregated branch hit counts
  <base>_inst_test_inputs_log.json  Inputs used per test case
  <base>_inst_report.html           Interactive branch coverage report
  <base>_inst_source.html           Syntax-highlighted source view
  summary_report.html               (directory mode) Overall summary across files


Coverage formula:
  coverage % = edges hit / edges that exist x 100
                A decision (if, loop, ?:) has 2 edges (true, false);
                a switch case/default label has 1 edge (the label is taken).
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

# Compiler flags shared by the Clang scan (instrument.py) and gcc, so branches are counted in
# the code that is actually compiled. Override from the environment, e.g.
#   CFLAGS="-DLARGE_INT=1000000 -I include" ./c2obra.sh file.c     (CFLAGS="" = no flags)
# Default: SV-COMP files use LARGE_INT without defining it (same value as cov_runtime.h).
CFLAGS="${CFLAGS--DLARGE_INT=1000000}"
read -ra CFLAGS_ARR <<< "$CFLAGS"

# Data model of the task (Test-Comp .yml: ILP32 or LP64). Added to CFLAGS_ARR so the Clang scan
# and gcc agree, and passed to Sikraken (which defaults to -m32). Unset: no flag, as before.
case "${DATA_MODEL:-}" in
  "")         SIK_DM="" ;;
  ILP32|-m32) SIK_DM="-m32" ;;
  LP64|-m64)  SIK_DM="-m64" ;;
  *) echo "❌ DATA_MODEL must be ILP32, LP64, -m32 or -m64 (got '$DATA_MODEL')"; exit 1 ;;
esac
[ -n "$SIK_DM" ] && CFLAGS_ARR+=("$SIK_DM")
read -ra LDLIBS_ARR <<< "${LDLIBS:-}"
echo "Compiler flags (CFLAGS): ${CFLAGS_ARR[*]:-(none)}"


# Returns 0 if Sikraken is installed and usable
sikraken_available() {
  [ -d "$SIKRAKEN_DIR" ] && [ -f "$SIKRAKEN_DIR/bin/sikraken.sh" ]
}


# ─── SINGLE FILE MODE ─────────────────────────────────────────────────────────
if [ -f "$1" ]; then
    SRC="$1"
    BASENAME=$(basename "$SRC"); BASENAME="${BASENAME%.[ci]}"
    OUT="${OUT_DIR:-output}"; BUILD="${OUT_DIR:-build}"
    RUN_CWD="${OUT_DIR:-.}"   # run_tests.py writes output/coverage_report.json relative to its cwd
    mkdir -p "$OUT" "$BUILD"

    # Auto-detect: does the file use __VERIFIER_nondet inputs?
    if [ -n "${SIKRAKEN_SUITE:-}" ]; then
        SUITE_DIR="$SIKRAKEN_SUITE"
        echo "=== Test suite given (SIKRAKEN_SUITE): $SUITE_DIR — Sikraken not run ==="
    elif grep -q "__VERIFIER_nondet" "$SRC"; then
        echo "=== Detected: input-driven file ==="
        if ! sikraken_available; then
            echo "⚠️  Sikraken not found at $SIKRAKEN_DIR — skipping, running with no inputs"
            SUITE_DIR="-"
        else
            echo "=== Step 0: Run Sikraken ==="
            ABS_SRC="$(realpath "$SRC")"
            REL_SRC="$(realpath --relative-to="$SIKRAKEN_DIR" "$ABS_SRC")"
            cd "$SIKRAKEN_DIR"
            ./bin/sikraken.sh release budget[10] ${SIK_DM:+"$SIK_DM"} "$REL_SRC"
            cd "$SCRIPT_DIR"
            # Exact path: Sikraken writes to sikraken_output/<file name without extension>/
            SUITE_DIR="$SIKRAKEN_OUT/$BASENAME/test-suite"
            [ -d "$SUITE_DIR" ] || SUITE_DIR=""
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
    # "|| ..." so set -e does not exit before the error message is shown
    INST_OUT=$(python3 src/instrument.py "$SRC" "$OUT/${BASENAME}_inst.c" -- "${CFLAGS_ARR[@]}") \
        || { echo "$INST_OUT"; echo "❌ Instrumentation failed (CFLAGS: ${CFLAGS_ARR[*]:-(none)})"; exit 1; }
    echo "$INST_OUT"
    BRANCH_COUNTERS=$(echo "$INST_OUT" | grep '^BRANCH_COUNTERS=' | cut -d= -f2)

    # Step 2: Compile instrumented source + runtime
    echo "=== Step 2: Compile ==="
    gcc "$OUT/${BASENAME}_inst.c" src/cov_runtime.c src/verifier_stubs.c \
        -o "$BUILD/${BASENAME}_test" -I src/ \
        -DMAX_BRANCHES=${BRANCH_COUNTERS:-131072} \
        "${CFLAGS_ARR[@]}" -w "${LDLIBS_ARR[@]}"
    [ -f "$BUILD/${BASENAME}_test" ] || { echo "❌ Compilation failed"; exit 1; }
    echo "✓ Binary built → $BUILD/${BASENAME}_test"

    # Step 3: Run tests and collect coverage
    echo "=== Step 3: Run Tests ==="
    SUITE_ARG="${SUITE_DIR:-"-"}"
    [ "$SUITE_ARG" = "-" ] || SUITE_ARG="$(realpath "$SUITE_ARG")"
    BIN_ABS="$(realpath "$BUILD/${BASENAME}_test")"
    MAP_ABS="$(realpath "$OUT/${BASENAME}_inst_branch_map.json")"
    RUN_TESTS="$(realpath src/run_tests.py)"
    (cd "$RUN_CWD" && python3 "$RUN_TESTS" "$BIN_ABS" "$SUITE_ARG" "$MAP_ABS")

    if [ -f "$RUN_CWD/output/test_inputs_log.json" ]; then
        mv "$RUN_CWD/output/test_inputs_log.json" "$OUT/${BASENAME}_inst_test_inputs_log.json"
    fi

    # Keep coverage_report.json in place for CI index aggregation (copy, not move)
    if [ -f "$RUN_CWD/output/coverage_report.json" ]; then
        cp "$RUN_CWD/output/coverage_report.json" "$OUT/${BASENAME}_inst_coverage.json"
        echo "✓ Saved coverage → $OUT/${BASENAME}_inst_coverage.json"
    else
        echo "⚠️ No coverage_report.json produced"
    fi

    # Step 4: Generate HTML report
    echo "=== Step 4: Report ==="
    python3 src/report.py \
        "$OUT/${BASENAME}_inst_branch_map.json" \
        "$OUT/${BASENAME}_inst_coverage.json" \
        --output      "$OUT/${BASENAME}_inst_report.html" \
        --csv         "$OUT/${BASENAME}_inst_report.csv" \
        --test-inputs "$OUT/${BASENAME}_inst_test_inputs_log.json" \
        --no-summary || true

    echo "✅ Done → open $OUT/${BASENAME}_inst_report.html"
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
    INST_OUTPUT=$(python3 src/instrument.py "$SRC" "$OUT_DIR" -- "${CFLAGS_ARR[@]}") \
        || { echo "$INST_OUTPUT"; echo "❌ Instrumentation failed (CFLAGS: ${CFLAGS:-(none)})"; exit 1; }
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
                # Exact path: Sikraken writes to sikraken_output/<file name without extension>/
                SUITE_DIR="$SIKRAKEN_OUT/$base/test-suite"
                [ -d "$SUITE_DIR" ] || SUITE_DIR=""
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
            "${CFLAGS_ARR[@]}" -w 2>/dev/null || true

        [ -f "build/${base}_test" ] || { echo "❌ Compilation failed for $base — skipping"; continue; }
        echo "✓ Built build/${base}_test"

        # Step 3: Run tests
        python3 src/run_tests.py \
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
        python3 src/report.py \
            "$OUT_DIR/${base}_inst_branch_map.json" \
            "$OUT_DIR/${base}_inst_coverage.json" \
            --output      "$OUT_DIR/${base}_inst_report.html" \
            --csv         "$OUT_DIR/${base}_inst_report.csv" \
            --test-inputs "$OUT_DIR/${base}_inst_test_inputs_log.json" || true
    done

    # Step 5: Generate summary report across all files
    echo ""
    echo "=== Summary Report ==="
    python3 src/merge_reports.py "$OUT_DIR"

    # Step 6: Write aggregate coverage_report.json for CI index page
    python3 - "$OUT_DIR" <<'PYEOF'
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