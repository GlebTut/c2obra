/* Backslash-newline splice and comments in awkward places. */
int x(int a) {
  if /* c1 */ (a > \
      2)
    return 1;
  while (a-- > 0 /* c2 */) ; // E: while
  return 0;
}
// E@3: if   (marker placed here because line 3 ends in a backslash splice)
