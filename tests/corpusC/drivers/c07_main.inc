/* Driver for c07_xmacro_switch.c: a main() appended to a copy of it by unittests/test_behaviour.py. */
#include <stdio.h>
int main(void) {
    printf("first_letter(RED) = %d\n", first_letter(RED));
    printf("first_letter(GREEN) = %d\n", first_letter(GREEN));
    printf("first_letter(BLUE) = %d\n", first_letter(BLUE));
    printf("first_letter(7) = %d\n", first_letter((enum colour)7));   /* no label matches */
    return 0;
}
