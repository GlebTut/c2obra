#include <stdio.h>

/*
 * Comprehensive test for branch coverage instrumentation
 * Tests: if statements, while loops, and for loops
 */

int main() {
    printf("=== Branch Coverage Test ===\n\n");

    // ===================================
    // Test 1: Simple if statement (both edges)
    // ===================================
    printf("Test 1: if statement (both edges)\n");
    for (int x = -5; x <= 5; x += 10) {
        if (x > 0) {
            printf("  x is positive\n");
        } else {
            printf("  x is not positive\n");
        }
    }

    // ===================================
    // Test 2: if statement (both edges via loop)
    // ===================================
    printf("\nTest 2: if statement (both edges)\n");
    for (int y = -3; y <= 3; y += 6) {
        if (y > 0) {
            printf("  y is positive\n");
        } else {
            printf("  y is not positive\n");
        }
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
    // Test 4: while loop (both edges)
    // ===================================
    printf("\nTest 4: while loop\n");
    int count = 0;
    while (count < 3) {
        printf("  count = %d\n", count);
        count++;
    }

    // ===================================
    // Test 5: while loop (iterates then exits)
    // ===================================
    printf("\nTest 5: while loop (iterates)\n");
    int n = 0;
    while (n < 5) {
        printf("  n = %d\n", n);
        n++;
    }
    printf("  Loop done (n=%d)\n", n);

    // ===================================
    // Test 6: for loop (both edges)
    // ===================================
    printf("\nTest 6: for loop\n");
    for (int i = 0; i < 5; i++) {
        printf("  i = %d\n", i);
    }

    // ===================================
    // Test 7: for loop (iterates)
    // ===================================
    printf("\nTest 7: for loop (iterates)\n");
    for (int j = 0; j < 3; j++) {
        printf("  j = %d\n", j);
    }

    // ===================================
    // Test 8: Nested if statements (all edges)
    // ===================================
    printf("\nTest 8: Nested if statements\n");
    int pairs[3][2] = {{5, 10}, {-1, 3}, {3, 1}};
    for (int p = 0; p < 3; p++) {
        int a = pairs[p][0], b = pairs[p][1];
        if (a > 0) {
            printf("  a is positive\n");
            if (b > a) {
                printf("  b is greater than a\n");
            } else {
                printf("  b is not greater than a\n");
            }
        } else {
            printf("  a is not positive\n");
        }
    }

    // ===================================
    // Test 9: Complex conditions (both edges)
    // ===================================
    printf("\nTest 9: Complex conditions\n");
    for (int val = 3; val <= 12; val += 4) {
        if (val > 5 && val < 10) {
            printf("  %d is between 5 and 10\n", val);
        } else {
            printf("  %d is out of range\n", val);
        }
    }

    printf("\n=== Test Complete ===\n");
    return 0;
}
