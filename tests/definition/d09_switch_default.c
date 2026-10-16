/* switch with default: one edge per label (case 1, case 2, default). */
int f(int v) {
  switch (v) {
    case 1: return 10;
    case 2: return 20;
    default: return 0;
  }
}
int main(void) { f(1); f(2); f(3); return 0; }
