#include <stdio.h>

/*
 * Master branch coverage test
 * Covers: if, if/else, else-if chains, for, while, do-while,
 *         switch, nested branches, mixed constructs
 */

/* Helper functions */
int is_even(int n)   { return n % 2 == 0; }
int is_positive(int n) { return n > 0; }

int main() {
    printf("=== Master Branch Coverage Test ===\n\n");

    // ===================================
    // Section 1: if statements
    // ===================================
    printf("-- Section 1: if statements --\n");

    // 1a: if only (both edges via loop)
    for (int x = -1; x <= 1; x += 2) {
        if (x > 0) {
            printf("  1a: x=%d positive\n", x);
        }
    }

    // 1b: if/else (both edges)
    for (int x = -1; x <= 1; x += 2) {
        if (x > 0) {
            printf("  1b: x=%d positive\n", x);
        } else {
            printf("  1b: x=%d not positive\n", x);
        }
    }

    // 1c: else-if chain (all branches)
    int vals[] = {-5, 0, 5, 15, 25};
    for (int i = 0; i < 5; i++) {
        int v = vals[i];
        if (v < 0) {
            printf("  1c: %d negative\n", v);
        } else if (v == 0) {
            printf("  1c: %d zero\n", v);
        } else if (v < 10) {
            printf("  1c: %d small\n", v);
        } else if (v < 20) {
            printf("  1c: %d medium\n", v);
        } else {
            printf("  1c: %d large\n", v);
        }
    }

    // 1d: nested if
    int pairs[4][2] = {{1,2},{1,0},{0,2},{0,0}};
    for (int i = 0; i < 4; i++) {
        int a = pairs[i][0], b = pairs[i][1];
        if (a > 0) {
            if (b > 0) {
                printf("  1d: a>0 b>0\n");
            } else {
                printf("  1d: a>0 b<=0\n");
            }
        } else {
            if (b > 0) {
                printf("  1d: a<=0 b>0\n");
            } else {
                printf("  1d: a<=0 b<=0\n");
            }
        }
    }

    // 1e: if with compound condition
    int data[] = {3, 7, 15, -1};
    for (int i = 0; i < 4; i++) {
        int v = data[i];
        if (v > 0 && v < 10) {
            printf("  1e: %d in (0,10)\n", v);
        } else {
            printf("  1e: %d out of (0,10)\n", v);
        }
    }

    // ===================================
    // Section 2: for loops
    // ===================================
    printf("\n-- Section 2: for loops --\n");

    // 2a: normal iteration (true + false edge)
    for (int i = 0; i < 3; i++) {
        printf("  2a: i=%d\n", i);
    }

    // 2b: zero iterations (false edge only — condition false from start)
    for (int i = 10; i > 3; i--) {
        printf("  2b: never\n");
    }
    printf("  2b: loop skipped\n");

    // 2c: nested for
    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 2; j++) {
            printf("  2c: i=%d j=%d\n", i, j);
        }
    }

    // 2d: for with break
    for (int i = 0; i < 10; i++) {
        if (i == 3) {
            printf("  2d: break at i=%d\n", i);
            break;
        }
        printf("  2d: i=%d\n", i);
    }

    // 2e: for with continue
    for (int i = 0; i < 5; i++) {
        if (i % 2 == 0) {
            continue;
        }
        printf("  2e: odd i=%d\n", i);
    }

    // ===================================
    // Section 3: while loops
    // ===================================
    printf("\n-- Section 3: while loops --\n");

    // 3a: normal while (both edges)
    int w = 0;
    while (w < 3) {
        printf("  3a: w=%d\n", w);
        w++;
    }

    // 3b: zero-iteration while (false edge only)
    int n = 10;
    while (n < 5) {
        printf("  3b: never\n");
        n++;
    }
    printf("  3b: skipped\n");

    // 3c: while with break
    int k = 0;
    while (1) {
        if (k >= 3) break;
        printf("  3c: k=%d\n", k);
        k++;
    }

    // 3d: nested while
    int p = 0;
    while (p < 2) {
        int q = 0;
        while (q < 2) {
            printf("  3d: p=%d q=%d\n", p, q);
            q++;
        }
        p++;
    }

    // ===================================
    // Section 4: do-while loops
    // ===================================
    printf("\n-- Section 4: do-while loops --\n");

    // 4a: do-while runs at least once
    int d = 0;
    do {
        printf("  4a: d=%d\n", d);
        d++;
    } while (d < 3);

    // 4b: do-while runs exactly once (condition false after first)
    int e = 5;
    do {
        printf("  4b: e=%d\n", e);
        e++;
    } while (e < 5);

    // ===================================
    // Section 5: switch statements
    // ===================================
    printf("\n-- Section 5: switch statements --\n");

    // 5a: basic switch — all cases + default
    int sv[] = {1, 2, 3, 99};
    for (int i = 0; i < 4; i++) {
        switch (sv[i]) {
            case 1:  printf("  5a: one\n");     break;
            case 2:  printf("  5a: two\n");     break;
            case 3:  printf("  5a: three\n");   break;
            default: printf("  5a: other\n");   break;
        }
    }

    // 5b: switch with fall-through
    int days[] = {1, 3, 7, 9};
    for (int i = 0; i < 4; i++) {
        switch (days[i]) {
            case 1:
            case 7:
                printf("  5b: day %d weekend\n", days[i]); break;
            case 2:
            case 3:
            case 4:
            case 5:
            case 6:
                printf("  5b: day %d weekday\n", days[i]); break;
            default:
                printf("  5b: day %d invalid\n", days[i]); break;
        }
    }

    // 5c: switch without default (implicit default)
    int codes[] = {10, 20, 99};
    for (int i = 0; i < 3; i++) {
        switch (codes[i]) {
            case 10: printf("  5c: ten\n");    break;
            case 20: printf("  5c: twenty\n"); break;
            case 30: printf("  5c: thirty\n"); break;
        }
    }

    // 5d: nested switch
    int ov[] = {1, 2, 3};
    int iv[] = {10, 20, 99};
    for (int i = 0; i < 3; i++) {
        switch (ov[i]) {
            case 1:
                switch (iv[i]) {
                    case 10:  printf("  5d: 1/10\n");    break;
                    case 20:  printf("  5d: 1/20\n");    break;
                    default:  printf("  5d: 1/other\n"); break;
                }
                break;
            case 2:
                switch (iv[i]) {
                    case 10:  printf("  5d: 2/10\n");    break;
                    case 20:  printf("  5d: 2/20\n");    break;
                    default:  printf("  5d: 2/other\n"); break;
                }
                break;
            default:
                printf("  5d: other\n"); break;
        }
    }

    // 5e: switch on expression
    for (int x = 0; x < 5; x++) {
        switch (x % 3) {
            case 0: printf("  5e: x=%d mod3=0\n", x); break;
            case 1: printf("  5e: x=%d mod3=1\n", x); break;
            case 2: printf("  5e: x=%d mod3=2\n", x); break;
        }
    }

    // ===================================
    // Section 6: mixed / complex
    // ===================================
    printf("\n-- Section 6: mixed constructs --\n");

    // 6a: switch inside if/else
    int flags[] = {1, 0};
    int modes[] = {1, 2, 3};
    for (int f = 0; f < 2; f++) {
        for (int m = 0; m < 3; m++) {
            if (flags[f]) {
                switch (modes[m]) {
                    case 1: printf("  6a: on/1\n"); break;
                    case 2: printf("  6a: on/2\n"); break;
                    default: printf("  6a: on/x\n"); break;
                }
            } else {
                switch (modes[m]) {
                    case 1: printf("  6a: off/1\n"); break;
                    case 2: printf("  6a: off/2\n"); break;
                    default: printf("  6a: off/x\n"); break;
                }
            }
        }
    }

    // 6b: if inside switch
    int sv2[] = {1, 2, 3, 4};
    for (int i = 0; i < 4; i++) {
        switch (sv2[i]) {
            case 1:
            case 2:
                if (sv2[i] == 1) {
                    printf("  6b: case1/2 → exactly 1\n");
                } else {
                    printf("  6b: case1/2 → exactly 2\n");
                }
                break;
            case 3:
                printf("  6b: case3\n"); break;
            default:
                printf("  6b: default\n"); break;
        }
    }

    // 6c: for + while + if combined
    for (int i = 0; i < 3; i++) {
        int j = 0;
        while (j < 2) {
            if (i + j > 2) {
                printf("  6c: i=%d j=%d sum>2\n", i, j);
            } else {
                printf("  6c: i=%d j=%d sum<=2\n", i, j);
            }
            j++;
        }
    }

    // 6d: function call in condition
    int nums[] = {-2, 0, 3, 4};
    for (int i = 0; i < 4; i++) {
        if (is_positive(nums[i])) {
            if (is_even(nums[i])) {
                printf("  6d: %d positive even\n", nums[i]);
            } else {
                printf("  6d: %d positive odd\n", nums[i]);
            }
        } else {
            printf("  6d: %d not positive\n", nums[i]);
        }
    }

    printf("\n=== Test Complete ===\n");
    return 0;
}
