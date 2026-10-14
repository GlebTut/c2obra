/* Macro inside a condition (harmless) vs macro that supplies the keyword itself. */
#define IS_NEG(x) ((x) < 0)
#define WHEN_POS(x) if ((x) > 0)
int g(int a) {
  if (IS_NEG(a))       // E: if
    return -1;
  WHEN_POS(a)          // E: if
    return 1;
  return 0;
}
