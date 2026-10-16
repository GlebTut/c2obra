/* for with a condition: 1 decision. */
int f(int n) { int s = 0; for (int i = 0; i < n; i++) s += i; return s; }
int main(void) { f(3); f(0); return 0; }
