/* K&R definition, dangling else, comma operator, condition-less for. */
int w(a, b)
  int a; int b;
{
  int i, j;
  for (;;) { break; }
  for (i = 0, j = 0; i < a; i++, j++)   // E: for
    if (i > b) if (j) a--; else b--;    // E: if if
  return a;
}
