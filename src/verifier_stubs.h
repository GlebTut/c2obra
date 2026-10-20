#ifndef VERIFIER_STUBS_H
#define VERIFIER_STUBS_H


extern void reach_error(void);
extern void __VERIFIER_error(void);
extern void __VERIFIER_assume(int);
extern int  __VERIFIER_nondet_int(void);
extern int  __VERIFIER_nondet_bool(void);

/* Additional nondet types */
extern float          __VERIFIER_nondet_float(void);
extern double         __VERIFIER_nondet_double(void);
extern char           __VERIFIER_nondet_char(void);
extern unsigned int   __VERIFIER_nondet_uint(void);
extern unsigned char  __VERIFIER_nondet_uchar(void);
extern short          __VERIFIER_nondet_short(void);
extern unsigned short __VERIFIER_nondet_ushort(void);
extern long           __VERIFIER_nondet_long(void);
extern long long      __VERIFIER_nondet_longlong(void);
extern unsigned int   __VERIFIER_nondet_unsigned(void);
extern unsigned int   __VERIFIER_nondet_u32(void);
extern unsigned long  __VERIFIER_nondet_ulong(void);
extern unsigned long long __VERIFIER_nondet_ulonglong(void);
extern size_t         __VERIFIER_nondet_size_t(void);   /* needs <stddef.h> */
extern void           __VERIFIER_nondet_memory(void *dst, size_t size);


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