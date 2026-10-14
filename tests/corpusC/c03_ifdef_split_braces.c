/* Conditional compilation that splits a statement header across #ifdef arms. */
int h(int a) {
#ifdef FAST
  if (a > 0) {         // E[FAST]: if
#else
  if (a >= 0) {        // E: if
#endif
    return 1;
  }
  return 0;
}
