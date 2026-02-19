#include "cov_runtime.h"

// This file is part of the SV-Benchmarks collection of verification tasks:
// https://github.com/sosy-lab/sv-benchmarks
//
// SPDX-FileCopyrightText: 2019 Philipp Berger, RWTH Aachen University
//
// SPDX-License-Identifier: Apache-2.0

extern void __assert_fail(const char *, const char *, unsigned int, const char *) __attribute__ ((__nothrow__ , __leaf__)) __attribute__ ((__noreturn__));
void reach_error() { __assert_fail("0", "deep-nested.c", 2, "reach_error"); }

int main() {
	unsigned a, b, c, d, e;

	unsigned uint32_max;
	uint32_max = 0xffffffff;

	for (a = 0;  cover(a < uint32_max - 1, 6) ; ++a) {
		for (b = 0;  cover(b < uint32_max - 1, 5) ; ++b) {
			for (c = 0;  cover(c < uint32_max - 1, 4) ; ++c) {
				for (d = 0;  cover(d < uint32_max - 1, 3) ; ++d) {
					for (e = 0;  cover(e < uint32_max - 1, 2) ; ++e) {
						if (cover((a == b) && (b == c) && (c == d) && (d == e) && (e == (uint32_max - 2)), 1)) {
							{reach_error();}
						}
					}
				}
			}
		}
	}

	return 0;
}
