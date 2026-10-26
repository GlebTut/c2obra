/* Driver for c04_dead_code.c: a main() appended to a copy of it by tests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("k(2) = %d\n", k(2));
    printf("k(3) = %d\n", k(3));
    printf("k(4) = %d\n", k(4));
    return 0;
}
