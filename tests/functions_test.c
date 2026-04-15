extern int __VERIFIER_nondet_int();


int fn1(int x) {
   if (0) return 0;  // true branch: CFG-reachable, compilation-time-unreachable
   if (x == 42) {
       if (x < 0) ; //compilation-time-reachable but semantically-unreachable
       return 1;
   }
   else return 2;
   //CFG-unreachable code below (dead code)
   if (x == 0) return 3;
   return 4;
}


int fn2(int x) {            //Semantically-Unreachable from main
   if (x == 42) return x;
   return x;
}


int fn3(int x) {            //Compilation-Time-Unreachable from main
   if (x == 42) return x;
   return x;
}


int fn4(int x) {            //CFG-Unreachable from main
   if (x == 42) return x;
   return x;
}


int fn5(int x) {            //not mentionned in main
   if (x == 42) return x;
   return x;
}


int main() {
   int b = __VERIFIER_nondet_int();
   if (0) fn3(b);  // true branch: CFG-reachable, compilation-time-unreachable
   if (b == 42) {
       fn1(b); //reachable
       if (b < 0) fn2(b); //compilation-time-reachable but semantically-unreachable
       return 1;
   }
   else return 0;              //reachable
   //all code after this is dead code (CFG-unreachable): the remaining branches can never be covered, including the all branches in the function fn4
   if (b == 43) return fn4(b);
   else return 0;
}
