#ifndef VERIFIER_STUBS_H
#define VERIFIER_STUBS_H

extern void reach_error(void);
extern void __VERIFIER_error(void);
extern void __VERIFIER_assume(int);
extern int  __VERIFIER_nondet_int(void);
extern int  __VERIFIER_nondet_bool(void);

/* Weak declaration so benchmarks can override with their own definition */
__attribute__((weak)) extern void __VERIFIER_assert(int);

/* Safe defaults for common SV-COMP constants benchmarks may reference */
#ifndef LARGE_INT
#define LARGE_INT 1000000
#endif

#ifndef SIZE
#define SIZE 100
#endif

#ifndef MAX
#define MAX 1000000
#endif

#endif /* VERIFIER_STUBS_H */
