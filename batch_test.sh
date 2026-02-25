#!/usr/bin/env bash
# batch_test.sh

FILES=(
    tests/benchmark02_linear.c
    tests/benchmark02_linear_abstracted.c
    tests/benchmark03_linear.c
    tests/benchmark04_conjunctive.c
    tests/benchmark05_conjunctive.c
    tests/benchmark06_conjunctive.c
    tests/benchmark07_linear.c
    tests/benchmark08_conjunctive.c
    tests/benchmark09_conjunctive.c
    tests/benchmark46_disjunctive.c
    tests/benchmark47_linear.c
)

for f in "${FILES[@]}"; do
    echo ""
    echo "========================================="
    echo "Testing: $f"
    echo "========================================="
    ./run_pipeline.sh "$f" || echo "❌ FAILED: $f"
done
