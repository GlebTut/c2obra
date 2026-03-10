#include <stdio.h>
extern int __VERIFIER_nondet_int();

int main() {
    int x = __VERIFIER_nondet_int();
    int y = __VERIFIER_nondet_int();

    // if statement
    if (x > 0) {
        printf("x positive\n");
    } else {
        printf("x not positive\n");
    }

    // for loop
    for (int i = 0; i < y; i++) {
        printf("loop %d\n", i);
    }

    // while loop
    while (x > 10) {
        x--;
    }

    // switch
    switch (x) {
        case 1: printf("one\n"); break;
        case 2: printf("two\n"); break;
        default: printf("other\n"); break;
    }

    return 0;
}
