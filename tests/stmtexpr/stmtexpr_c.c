extern int __VERIFIER_nondet_int(void);
/* GNU statement expressions in (a) assignment, (b) if, (c) for header, (d) while */
int main(void) {
  int x = __VERIFIER_nondet_int(), s = 0, i;
  int a = 0;
  for (i = ({ int t = 0; t; }); i < ({ int t = 2; t; }); i++)   /* (c) */
    s += i;
  return a + s; }
