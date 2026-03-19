# 0 "tests/benchmark_testing/benchmark01_conjunctive.c"
# 0 "<built-in>"
# 0 "<command-line>"
# 1 "/usr/include/stdc-predef.h" 1 3 4
# 0 "<command-line>" 2
# 1 "tests/benchmark_testing/benchmark01_conjunctive.c"
# 1 "/usr/include/assert.h" 1 3 4
# 35 "/usr/include/assert.h" 3 4
# 1 "/usr/include/features.h" 1 3 4
# 394 "/usr/include/features.h" 3 4
# 1 "/usr/include/features-time64.h" 1 3 4
# 20 "/usr/include/features-time64.h" 3 4
# 1 "/usr/include/bits/wordsize.h" 1 3 4
# 21 "/usr/include/features-time64.h" 2 3 4
# 1 "/usr/include/bits/timesize.h" 1 3 4
# 19 "/usr/include/bits/timesize.h" 3 4
# 1 "/usr/include/bits/wordsize.h" 1 3 4
# 20 "/usr/include/bits/timesize.h" 2 3 4
# 22 "/usr/include/features-time64.h" 2 3 4
# 395 "/usr/include/features.h" 2 3 4
# 502 "/usr/include/features.h" 3 4
# 1 "/usr/include/sys/cdefs.h" 1 3 4
# 576 "/usr/include/sys/cdefs.h" 3 4
# 1 "/usr/include/bits/wordsize.h" 1 3 4
# 577 "/usr/include/sys/cdefs.h" 2 3 4
# 1 "/usr/include/bits/long-double.h" 1 3 4
# 578 "/usr/include/sys/cdefs.h" 2 3 4
# 503 "/usr/include/features.h" 2 3 4
# 526 "/usr/include/features.h" 3 4
# 1 "/usr/include/gnu/stubs.h" 1 3 4






# 1 "/usr/include/gnu/stubs-32.h" 1 3 4
# 8 "/usr/include/gnu/stubs.h" 2 3 4
# 527 "/usr/include/features.h" 2 3 4
# 36 "/usr/include/assert.h" 2 3 4
# 66 "/usr/include/assert.h" 3 4




# 69 "/usr/include/assert.h" 3 4
extern void __assert_fail (const char *__assertion, const char *__file,
      unsigned int __line, const char *__function)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));


extern void __assert_perror_fail (int __errnum, const char *__file,
      unsigned int __line, const char *__function)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));




extern void __assert (const char *__assertion, const char *__file, int __line)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));



# 2 "tests/benchmark_testing/benchmark01_conjunctive.c" 2

# 2 "tests/benchmark_testing/benchmark01_conjunctive.c"
void reach_error(void) {
# 2 "tests/benchmark_testing/benchmark01_conjunctive.c" 3 4
                       ((void) sizeof ((
# 2 "tests/benchmark_testing/benchmark01_conjunctive.c"
                       0
# 2 "tests/benchmark_testing/benchmark01_conjunctive.c" 3 4
                       ) ? 1 : 0), __extension__ ({ if (
# 2 "tests/benchmark_testing/benchmark01_conjunctive.c"
                       0
# 2 "tests/benchmark_testing/benchmark01_conjunctive.c" 3 4
                       ) ; else __assert_fail (
# 2 "tests/benchmark_testing/benchmark01_conjunctive.c"
                       "0"
# 2 "tests/benchmark_testing/benchmark01_conjunctive.c" 3 4
                       , "tests/benchmark_testing/benchmark01_conjunctive.c", 2, __extension__ __PRETTY_FUNCTION__); }))
# 2 "tests/benchmark_testing/benchmark01_conjunctive.c"
                                ;}

extern int __VERIFIER_nondet_int(void);
extern _Bool __VERIFIER_nondet_bool(void);

void __VERIFIER_assert(int cond) {
  if (!cond) {
    reach_error();
  }
}
# 24 "tests/benchmark_testing/benchmark01_conjunctive.c"
int main() {
  int x = __VERIFIER_nondet_int();
  int y = __VERIFIER_nondet_int();

  if (!(x==1 && y==1)) return 0;
  while (__VERIFIER_nondet_bool()) {
    x=x+y;
    y=x;
  }
  __VERIFIER_assert(y>=1);
  return 0;
}
