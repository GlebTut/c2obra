/*
 * example_coverage.c
 *
 * A comprehensive C example designed to exercise branch coverage:
 *   - if/else chains
 *   - nested conditions
 *   - for / while / do-while loops
 *   - switch/case
 *   - logical operators (&&, ||)
 *   - __VERIFIER_nondet inputs (Sikraken compatible)
 *
 * Build & run via the pipeline:
 *   ./run_pipeline.sh tests/examples/example_coverage.c
 */

#include <stdio.h>

/* Verifier stubs for Sikraken / SV-COMP */
extern int   __VERIFIER_nondet_int(void);
extern char  __VERIFIER_nondet_char(void);

/* ── helpers ──────────────────────────────────────────────────── */

/* Classify an integer into a named category */
static const char *classify_number(int n) {
    if (n < 0) {
        if (n < -100) {
            return "very negative";
        } else {
            return "negative";
        }
    } else if (n == 0) {
        return "zero";
    } else if (n <= 10) {
        return "small positive";
    } else if (n <= 100) {
        return "medium positive";
    } else {
        return "large positive";
    }
}

/* Return 1 if n is prime, 0 otherwise */
static int is_prime(int n) {
    if (n < 2) return 0;
    if (n == 2) return 1;
    if (n % 2 == 0) return 0;
    for (int i = 3; i * i <= n; i += 2) {
        if (n % i == 0) return 0;
    }
    return 1;
}

/* Compute nth Fibonacci number iteratively */
static int fibonacci(int n) {
    if (n <= 0) return 0;
    if (n == 1) return 1;
    int a = 0, b = 1;
    for (int i = 2; i <= n; i++) {
        int tmp = a + b;
        a = b;
        b = tmp;
    }
    return b;
}

/* Grade a score 0-100 */
static char grade(int score) {
    if (score < 0 || score > 100) return '?';
    if (score >= 90) return 'A';
    if (score >= 80) return 'B';
    if (score >= 70) return 'C';
    if (score >= 60) return 'D';
    return 'F';
}

/* FizzBuzz — returns: 0=FizzBuzz, 1=Fizz, 2=Buzz, 3=Other */
static int fizzbuzz_kind(int n) {
    int div3 = (n % 3 == 0);
    int div5 = (n % 5 == 0);
    if (div3 && div5) return 0;
    if (div3)         return 1;
    if (div5)         return 2;
    return 3;
}

/* Simple stack-based expression: evaluate sign of (a*b - c) */
static int sign_of_expr(int a, int b, int c) {
    int val = a * b - c;
    if (val > 0)      return  1;
    else if (val < 0) return -1;
    else              return  0;
}

/* Count vowels in a string (only lowercase a-z checked) */
static int count_vowels(const char *s) {
    int count = 0;
    while (*s) {
        char ch = *s++;
        switch (ch) {
            case 'a': case 'e': case 'i': case 'o': case 'u':
                count++;
                break;
            default:
                break;
        }
    }
    return count;
}

/* Caesar cipher: shift letters by `shift`, leave others unchanged */
static char caesar_char(char c, int shift) {
    shift = ((shift % 26) + 26) % 26;   /* normalise to 0-25 */
    if (c >= 'a' && c <= 'z') {
        return (char)('a' + (c - 'a' + shift) % 26);
    } else if (c >= 'A' && c <= 'Z') {
        return (char)('A' + (c - 'A' + shift) % 26);
    }
    return c;   /* non-alpha: unchanged */
}

/* Collatz steps: count steps to reach 1 from n (n > 0) */
static int collatz_steps(int n) {
    if (n <= 0) return -1;
    int steps = 0;
    while (n != 1) {
        if (n % 2 == 0) {
            n /= 2;
        } else {
            n = 3 * n + 1;
        }
        steps++;
        if (steps > 10000) return -1;   /* safety guard */
    }
    return steps;
}

/* Triangle classifier */
typedef enum { INVALID, EQUILATERAL, ISOSCELES, SCALENE } Triangle;

static Triangle classify_triangle(int a, int b, int c) {
    if (a <= 0 || b <= 0 || c <= 0)           return INVALID;
    if (a + b <= c || a + c <= b || b + c <= a) return INVALID;
    if (a == b && b == c)                       return EQUILATERAL;
    if (a == b || b == c || a == c)             return ISOSCELES;
    return SCALENE;
}

/* ── main ─────────────────────────────────────────────────────── */

int main(void) {

    /* --- 1. Read two integers via nondet (Sikraken will fuzz these) --- */
    int x = __VERIFIER_nondet_int();
    int y = __VERIFIER_nondet_int();

    /* --- 2. Number classification --- */
    printf("x=%d → %s\n", x, classify_number(x));
    printf("y=%d → %s\n", y, classify_number(y));

    /* --- 3. Prime check --- */
    if (is_prime(x)) {
        printf("%d is prime\n", x);
    } else {
        printf("%d is not prime\n", x);
    }

    /* --- 4. Fibonacci (bounded to avoid huge numbers) --- */
    int fib_n = x < 0 ? -x : x;
    if (fib_n > 20) fib_n = fib_n % 20;
    printf("fib(%d) = %d\n", fib_n, fibonacci(fib_n));

    /* --- 5. Grade score --- */
    int score = y < 0 ? -y : y;
    score = score % 101;    /* clamp to 0-100 */
    printf("score=%d → grade=%c\n", score, grade(score));

    /* --- 6. FizzBuzz for a small range driven by x --- */
    int start = x < 0 ? 0 : x % 16;
    for (int i = start; i < start + 15; i++) {
        int kind = fizzbuzz_kind(i);
        switch (kind) {
            case 0: printf("FizzBuzz\n"); break;
            case 1: printf("Fizz\n");     break;
            case 2: printf("Buzz\n");     break;
            default: printf("%d\n", i);  break;
        }
    }

    /* --- 7. Sign of expression --- */
    int a = __VERIFIER_nondet_int();
    int b = __VERIFIER_nondet_int();
    int c_val = __VERIFIER_nondet_int();
    int s = sign_of_expr(a, b, c_val);
    if (s > 0)       printf("a*b - c is positive\n");
    else if (s < 0)  printf("a*b - c is negative\n");
    else             printf("a*b - c is zero\n");

    /* --- 8. Vowel counter on a short string driven by nondet char --- */
    char ch = __VERIFIER_nondet_char();
    /* Build a tiny two-char string for counting */
    char word[3] = {ch, 'e', '\0'};
    int vowels = count_vowels(word);
    if (vowels == 2)       printf("both chars are vowels\n");
    else if (vowels == 1)  printf("one vowel found\n");
    else                   printf("no vowels\n");

    /* --- 9. Caesar cipher on the same char --- */
    char enc = caesar_char(ch, y % 26);
    if (enc != ch)  printf("char shifted: %c → %c\n", ch, enc);
    else            printf("char unchanged: %c\n", ch);

    /* --- 10. Collatz steps --- */
    int cn = x < 0 ? -x : x;
    if (cn == 0) cn = 1;
    if (cn > 50) cn = cn % 50 + 1;
    int steps = collatz_steps(cn);
    if (steps < 0)       printf("collatz guard hit\n");
    else if (steps == 0) printf("collatz: already at 1\n");
    else                 printf("collatz(%d): %d steps\n", cn, steps);

    /* --- 11. Triangle classifier --- */
    int t1 = __VERIFIER_nondet_int();
    int t2 = __VERIFIER_nondet_int();
    int t3 = __VERIFIER_nondet_int();
    Triangle tri = classify_triangle(t1, t2, t3);
    switch (tri) {
        case EQUILATERAL: printf("equilateral triangle\n");  break;
        case ISOSCELES:   printf("isosceles triangle\n");    break;
        case SCALENE:     printf("scalene triangle\n");      break;
        default:          printf("invalid triangle\n");      break;
    }

    /* --- 12. do-while loop: countdown until condition met --- */
    int counter = (x % 8 + 8) % 8;   /* 0..7 */
    do {
        counter--;
        if (counter < 0) break;
    } while (counter > 0);
    printf("countdown done\n");

    /* --- 13. Nested logical operators --- */
    int p = __VERIFIER_nondet_int();
    int q = __VERIFIER_nondet_int();
    if ((p > 0 && q > 0) || (p < 0 && q < 0)) {
        printf("same sign\n");
    } else if (p == 0 || q == 0) {
        printf("at least one zero\n");
    } else {
        printf("opposite signs\n");
    }

    return 0;
}
