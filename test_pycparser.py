#!/usr/bin/env python3
"""
Test script for pycparser with large C files
Tests parsing performance and code analysis on Problem08_label20.c
"""

import time
from pycparser import c_parser, c_ast
import re

print("Testing Problem08_label20.c with pycparser...")
print("="*70)

# Step 1: Read the file
print("\n1. Reading file...")
with open('Problem08_label20.c', 'r') as f:
    c_code = f.read()

print(f"   Size: {len(c_code):,} characters, {len(c_code.splitlines()):,} lines")

# Step 2: Preprocessing (remove comments and GCC attributes)
print("\n2. Removing comments and GCC attributes...")
start = time.time()
c_code = re.sub(r'//.*?$', '', c_code, flags=re.MULTILINE)
c_code = re.sub(r'/\*.*?\*/', '', c_code, flags=re.DOTALL)
c_code = re.sub(r'__attribute__\s*\(\(.*?\)\)', '', c_code, flags=re.DOTALL)
prep_time = time.time() - start
print(f"   Time: {prep_time:.4f} seconds")

# Step 3: Parse the code
print("\n3. Parsing code (may take several minutes for large files)...")
parser = c_parser.CParser()
start = time.time()

try:
    ast = parser.parse(c_code, filename='Problem08_label20.c')
    parse_time = time.time() - start
    print(f"   ✓ Success! Time: {parse_time:.2f} seconds")

    # Step 4: Analyze the code structure
    print("\n4. Analyzing code structure...")

    class CodeAnalyzer(c_ast.NodeVisitor):
        def __init__(self):
            self.functions = []
            self.if_count = 0
            self.switch_count = 0
            self.case_count = 0
            self.while_count = 0
            self.for_count = 0
            self.assignments = 0
            self.func_calls = 0

        def visit_FuncDef(self, node):
            self.functions.append(node.decl.name)
            self.generic_visit(node)

        def visit_If(self, node):
            self.if_count += 1
            self.generic_visit(node)

        def visit_Switch(self, node):
            self.switch_count += 1
            self.generic_visit(node)

        def visit_Case(self, node):
            self.case_count += 1
            self.generic_visit(node)

        def visit_While(self, node):
            self.while_count += 1
            self.generic_visit(node)

        def visit_For(self, node):
            self.for_count += 1
            self.generic_visit(node)

        def visit_Assignment(self, node):
            self.assignments += 1
            self.generic_visit(node)

        def visit_FuncCall(self, node):
            self.func_calls += 1
            self.generic_visit(node)

    start = time.time()
    analyzer = CodeAnalyzer()
    analyzer.visit(ast)
    analysis_time = time.time() - start

    print(f"   ✓ Analysis complete! Time: {analysis_time:.2f} seconds")

    # Display results
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    print(f"Functions:          {len(analyzer.functions):>10,}")
    print(f"If statements:      {analyzer.if_count:>10,}")
    print(f"Switch statements:  {analyzer.switch_count:>10,}")
    print(f"Case labels:        {analyzer.case_count:>10,}")
    print(f"While loops:        {analyzer.while_count:>10,}")
    print(f"For loops:          {analyzer.for_count:>10,}")
    print(f"Assignments:        {analyzer.assignments:>10,}")
    print(f"Function calls:     {analyzer.func_calls:>10,}")

    print(f"\nFirst 10 functions:")
    for i, func in enumerate(analyzer.functions[:10], 1):
        print(f"  {i}. {func}")

    if len(analyzer.functions) > 10:
        print(f"  ... and {len(analyzer.functions) - 10} more")

    print("\n" + "="*70)
    print("PERFORMANCE:")
    print("="*70)
    total_time = prep_time + parse_time + analysis_time
    print(f"Preprocessing:  {prep_time:>8.2f} sec")
    print(f"Parsing:        {parse_time:>8.2f} sec")
    print(f"Analysis:       {analysis_time:>8.2f} sec")
    print(f"{'─'*35}")
    print(f"TOTAL:          {total_time:>8.2f} sec")

    # Calculate metrics
    lines = len(c_code.splitlines())
    print(f"\nParsing speed: {len(c_code)/parse_time/1000:.2f} thousand chars/sec")
    print(f"Lines per second: {lines/parse_time:,.0f}")

    print("\n" + "="*70)
    print("✓ TEST COMPLETED SUCCESSFULLY")
    print("="*70)

except Exception as e:
    elapsed = time.time() - start
    print(f"\n✗ Error occurred!")
    print(f"   Time elapsed: {elapsed:.4f} seconds")
    print(f"   Error type: {type(e).__name__}")
    print(f"   Message: {str(e)[:200]}")
    print("\n   Note: Large files (>5MB) may timeout or fail with pycparser.")
    print("   Consider using libclang or strstr scanner for production use.")
