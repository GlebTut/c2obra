/* Driver for c01_macro_with_if.c: a main() appended to a copy of it by tests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("f(3, 4) = %d\n", f(3, 4));
    printf("f(12, 5) = %d\n", f(12, 5));
    printf("f(20, 30) = %d\n", f(20, 30));
    return 0;
}
