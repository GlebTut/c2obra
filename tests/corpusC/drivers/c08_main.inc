/* Driver for c08_ternary_macros.c: a main() appended to a copy of it by unittests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("t(1, 2, 3) = %d\n", t(1, 2, 3));
    printf("t(5, 1, 2) = %d\n", t(5, 1, 2));
    printf("t(-4, -9, -1) = %d\n", t(-4, -9, -1));
    return 0;
}
