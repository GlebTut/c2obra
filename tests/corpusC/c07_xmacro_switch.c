/* X-macro generating enum members and switch case labels. */
#define COLOURS X(RED) X(GREEN) X(BLUE)
enum colour {
#define X(n) n,
  COLOURS
#undef X
};
int first_letter(enum colour v) {
  switch (v) {            // E: switch
#define X(n) case n: return #n[0];
    COLOURS
#undef X
  }
  return 0;
}
