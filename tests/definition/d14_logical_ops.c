/* && and || are inside ONE decision (decision-level): 2 edges, not one per operand. */
int f(int a, int b, int c) {
  if ((a && b) || c) return 1;
  return 0;
}
int main(void) { f(1, 1, 0); f(0, 0, 0); return 0; }
