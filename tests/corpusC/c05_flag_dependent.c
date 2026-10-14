/* Branch set depends on -D flags: the tool must use the real build flags. */
#include <stdio.h>
int m(int a) {
#ifdef DEBUG
  if (a < 0) printf("neg\n");   // E[DEBUG]: if
#endif
  for (int i = 0; i < a; i++)   // E: for
    a--;
  return a;
}
