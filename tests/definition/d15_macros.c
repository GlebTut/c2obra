/* Decisions that exist only inside macros are not counted (reported as skipped). */
#include <assert.h>
#define MAX(a, b) ((a) > (b) ? (a) : (b))
int f(int x, int y) {
  int m = MAX(x, y);           /* macro: contains ?: */
  assert(m >= 0);              /* macro: contains a decision */
  if (m > 5)                   /* the only decision written in the file */
    return 1;
  return 0;
}
int main(void) { f(3, 4); return 0; }
