extern int __VERIFIER_nondet_int(void);
/* GNU statement expressions in (a) assignment, (b) if, (c) for header, (d) while */
int main(void) {
  int x = __VERIFIER_nondet_int(), s = 0, i;
  int a = 0;
  if (({ int t = x; t > 3; }))                                  /* (b) */
    s = 1;
  return a + s; }
