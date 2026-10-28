/* Driver for c02_macro_condition_and_keyword.c: a main() appended to a copy of it by unittests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("g(-5) = %d\n", g(-5));
    printf("g(0) = %d\n", g(0));
    printf("g(7) = %d\n", g(7));
    return 0;
}
