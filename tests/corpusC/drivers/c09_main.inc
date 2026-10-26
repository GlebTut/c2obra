/* Driver for c09_gnu_extensions.c: a main() appended to a copy of it by tests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("u(3, 7) = %d\n", u(3, 7));
    printf("u(0, 4) = %d\n", u(0, 4));
    printf("u(9, 2) = %d\n", u(9, 2));
    return 0;
}
