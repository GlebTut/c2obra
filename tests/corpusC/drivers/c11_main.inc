/* Driver for c11_kr_and_oddities.c: a main() appended to a copy of it by tests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("w(3, 1) = %d\n", w(3, 1));
    printf("w(5, 0) = %d\n", w(5, 0));
    printf("w(2, -1) = %d\n", w(2, -1));   /* reaches the else */
    printf("w(0, 0) = %d\n", w(0, 0));
    return 0;
}
