/* for(;;): no condition expression. CONFIRMED 2026-10-16: counted like while(1) (2 edges). */
int f(int x) {
  int i = 0;
  for (;;) {                   /* decision 1 (if counted) */
    if (++i > x) break;        /* decision 2 */
  }
  return i;
}
int main(void) { f(2); f(0); return 0; }
