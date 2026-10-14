/* Loop header supplied by a macro. */
#define REPEAT(n) for (int i_ = 0; i_ < (n); i_++)
#define FOREVER_UNTIL(c) while (!(c))
int r(int n) {
  int s = 0;
  REPEAT(n) s += 2;        // E: for
  FOREVER_UNTIL(s < 10)    // E: while
    s -= 3;
  return s;
}
