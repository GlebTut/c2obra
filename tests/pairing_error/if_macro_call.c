/* The condition of this `if` is a macro call written without parentheses of its own:
   Clang sees the decision, but there is no plain condition text to wrap, so instrument.py
   stops with a pairing error (it does not guess). */
#define COND(x) (x > 1)
int main(void) {
  int i = 2;
  if COND(i) i++;
  return i;
}
