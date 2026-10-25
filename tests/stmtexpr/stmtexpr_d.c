extern int __VERIFIER_nondet_int(void);
/* GNU statement expressions in (a) assignment, (b) if, (c) for header, (d) while */
int main(void) {
  int x = __VERIFIER_nondet_int(), s = 0, i;
  int a = 0;
  while (({ int t = s; t > 0; }))                               /* (d) */
    s--;
  return a + s; }
