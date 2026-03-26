/*
 * simple_if.c — Minimal example for the C Testing Coverage Tool smoke test.
 *
 * This file contains 2 branch constructs = 4 branches total.
 * A complete test suite should cover all 4 branches (100%).
 *
 * Build and run via:
 *   bash smoke_test.sh
 */
#include <stdio.h>
extern int __VERIFIER_nondet_int(void);

int main(void) {
    int x = __VERIFIER_nondet_int();

    /* Branch 1: true = x > 0,  false = x <= 0 */
    if (x > 0) {
        printf("positive\n");
    } else {
        printf("non-positive\n");
    }

    /* Branch 2: true = even,  false = odd */
    if (x % 2 == 0) {
        printf("even\n");
    } else {
        printf("odd\n");
    }

    return 0;
}
