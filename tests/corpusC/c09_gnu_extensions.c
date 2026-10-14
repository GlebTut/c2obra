/* GNU C used in real code and in some SV-COMP files. */
int u(int a, int b) {
  int c = a ?: b;                                  // E: ?:
  int d = ({ int t_ = a; if (t_ > b) t_ = b; t_; }); // E: if
  switch (a) {                                     // E: switch
  case 1 ... 5: return c;
  default: break;
  }
  __typeof__(a) e = d;
  return e;
}
