#ifdef GCOV
extern void __gcov_dump(void);
#endif





extern void __assert_fail (const char *__assertion, const char *__file,
      unsigned int __line, const char *__function)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));


extern void __assert_perror_fail (int __errnum, const char *__file,
      unsigned int __line, const char *__function)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));




extern void __assert (const char *__assertion, const char *__file, int __line)
     __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));





int f(int x, int y) {
  int m = ((x) > (y) ? ({
goto Goal_1;
Goal_1:;
(x);}) : ({
goto Goal_2;
Goal_2:;
(y);}));
  
 ((void) sizeof ((
 m >= 0
 ) ? ({
goto Goal_3;
Goal_3:;
1;}) : ({
goto Goal_4;
Goal_4:;
0;})), __extension__ ({ if (
 m >= 0
 ) 
goto Goal_5;
Goal_5:;
 else 
goto Goal_6;
Goal_6:;

#ifdef GCOV
__gcov_dump();
#endif
__assert_fail (
 "m >= 0"
 , "/home/glebt/c2obra/tests/definition/d15_macros.c", 6, __extension__ __PRETTY_FUNCTION__); }))
               ;
  if (m > 5) {
goto Goal_7;
Goal_7:;

    return 1;
}
   else { 
goto Goal_8;
Goal_8:;
}return 0;
}
int main(void) { f(3, 4); return 0; }
