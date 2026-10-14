/* Control flow hidden inside a function-like macro (common in zlib/Linux). */
#define CLAMP(x) do { if ((x) > 10) (x) = 10; } while (0)
int f(int a, int b) {
  CLAMP(a);            // E: do if
  CLAMP(b);            // E: do if
  return a + b;
}
