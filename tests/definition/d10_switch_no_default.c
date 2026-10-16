/* switch without default: edges = case 1, case 2, implicit default (no label matched). CONFIRMED 2026-10-16. */
int f(int v) {
  switch (v) {
    case 1: return 10;
    case 2: return 20;
  }
  return 0;
}
int main(void) { f(1); f(2); return 0; }
