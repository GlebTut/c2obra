#!/usr/bin/env bash
# smoke_test.sh — Quick sanity check after install.
# Usage: bash scripts/smoke_test.sh   (from the repo root)
# Expected: 4 branches, 100% coverage (2 branch constructs × 2 edges each)

set -euo pipefail
TOOL_DIR="$(cd "$(dirname "$0")/.." && pwd)"   # repo root (this script is in scripts/)
# Same as c2obra.sh: use the project venv (the system python3 has no tree_sitter)
if [ -f "$TOOL_DIR/venv/bin/activate" ]; then
    source "$TOOL_DIR/venv/bin/activate"
fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Compiler flags shared by the Clang scan (instrument.py) and gcc, so branches are counted in
# the code that is actually compiled. Override from the environment, e.g.
#   CFLAGS="-DLARGE_INT=1000000 -I include" bash scripts/smoke_test.sh     (CFLAGS="" = no flags)
# Default: SV-COMP files use LARGE_INT without defining it (same value as cov_runtime.h).
CFLAGS="${CFLAGS--DLARGE_INT=1000000}"
read -ra CFLAGS_ARR <<< "$CFLAGS"
echo "Compiler flags (CFLAGS): ${CFLAGS:-(none)}"

cat > "$TMP/smoke.c" << 'EOF'
#include <stdio.h>
extern int __VERIFIER_nondet_int(void);

int main(void) {
    int x = __VERIFIER_nondet_int();
    if (x > 0) {
        printf("positive\n");
    } else {
        printf("non-positive\n");
    }

    int i = __VERIFIER_nondet_int();
    if (i % 2 == 0) {
        printf("even\n");
    } else {
        printf("odd\n");
    }
    return 0;
}
EOF

# Generate two test inputs: one positive/even, one negative/odd
mkdir -p "$TMP/suite"
cat > "$TMP/suite/test_input-1.xml" << 'EOF'
<tests><input>4</input><input>2</input></tests>
EOF
cat > "$TMP/suite/test_input-2.xml" << 'EOF'
<tests><input>-1</input><input>3</input></tests>
EOF

echo "=== Smoke Test: instrumenting smoke.c ==="
python3 "$TOOL_DIR/src/instrument.py" "$TMP/smoke.c" "$TMP/smoke_inst.c" -- "${CFLAGS_ARR[@]}"

echo ""
echo "=== Compiling ==="
COUNTERS=$(grep 'BRANCH_COUNTERS=' "$TMP/smoke_inst.c" 2>/dev/null | tail -1 | cut -d= -f2 || echo 4)
gcc -o "$TMP/smoke_bin" "$TMP/smoke_inst.c" "$TOOL_DIR/src/cov_runtime.c" "$TOOL_DIR/src/verifier_stubs.c" \
    -I"$TOOL_DIR/src" -DMAX_BRANCHES="${COUNTERS}" "${CFLAGS_ARR[@]}" -lm

echo ""
echo "=== Running tests ==="
python3 "$TOOL_DIR/src/run_tests.py" "$TMP/smoke_bin" "$TMP/suite" "$TMP/smoke_inst_branch_map.json"

echo ""
echo "=== Generating HTML report ==="
python3 "$TOOL_DIR/src/report.py" \
    "$TMP/smoke_inst_branch_map.json" \
    output/coverage_report.json \
    --output smoke_report.html

echo ""
echo "✅ Smoke test passed. Open smoke_report.html to view coverage."
echo "   Expected: 4 branches, 100% coverage."
