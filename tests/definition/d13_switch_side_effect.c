/* Behaviour preservation: the switch expression must be evaluated once. Original exits with 1. */
int main(void) {
  int i = 0;
  switch (i++) {
    case 0: break;
    case 1: break;
  }
  return i;
}
