#include <stdio.h>
extern int __VERIFIER_nondet_int();

int main() {
    int x = __VERIFIER_nondet_int();
    switch (x) {
        case 1: printf("one\n"); break;
        case 2: printf("two\n"); break;
        default: printf("other\n"); break;
    }
    return 0;
}
