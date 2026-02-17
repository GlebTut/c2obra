#include <stdio.h>

/*
 * Comprehensive test for branch coverage instrumentation
 * Tests: if statements, while loops, and for loops
 */

int main() {
    printf("=== Branch Coverage Test ===\n\n");

    // ===================================
    // Test 1: Simple if statement (true)
    // ===================================
    printf("Test 1: if statement (true)\n");
    int x = 5;
    if (x > 0) {
        printf("  x is positive\n");
    }

    // ===================================
    // Test 2: if statement (false)
    // ===================================
    printf("\nTest 2: if statement (false)\n");
    int y = -3;
    if (y > 0) {
        printf("  This should not print\n");
    } else {
        printf("  y is not positive\n");
    }

    // ===================================
    // Test 3: if statement (both paths)
    // ===================================
    printf("\nTest 3: if statement (both paths)\n");
    for (int i = -1; i <= 1; i++) {
        if (i > 0) {
            printf("  %d is positive\n", i);
        } else {
            printf("  %d is not positive\n", i);
        }
    }

    // ===================================
    // Test 4: while loop
    // ===================================
    printf("\nTest 4: while loop\n");
    int count = 0;
    while (count < 3) {
        printf("  count = %d\n", count);
        count++;
    }

    // ===================================
    // Test 5: while loop (zero iterations)
    // ===================================
    printf("\nTest 5: while loop (zero iterations)\n");
    int n = 10;
    while (n < 5) {
        printf("  This should not print\n");
        n++;
    }
    printf("  Loop never executed (n=%d >= 5)\n", n);

    // ===================================
    // Test 6: for loop
    // ===================================
    printf("\nTest 6: for loop\n");
    for (int i = 0; i < 5; i++) {
        printf("  i = %d\n", i);
    }

    // ===================================
    // Test 7: for loop (zero iterations)
    // ===================================
    printf("\nTest 7: for loop (zero iterations)\n");
    for (int j = 10; j < 5; j++) {
        printf("  This should not print\n");
    }
    printf("  Loop never executed\n");

    // ===================================
    // Test 8: Nested if statements
    // ===================================
    printf("\nTest 8: Nested if statements\n");
    int a = 5, b = 10;
    if (a > 0) {
        printf("  a is positive\n");
        if (b > a) {
            printf("  b is greater than a\n");
        }
    }

    // ===================================
    // Test 9: Multiple conditions
    // ===================================
    printf("\nTest 9: Complex conditions\n");
    int val = 7;
    if (val > 5 && val < 10) {
        printf("  val is between 5 and 10\n");
    }

    printf("\n=== Test Complete ===\n");
    return 0;
}