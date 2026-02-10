#!/usr/bin/env python3
"""
Simple pycparser test for Problem08_label20.c
Same operations as tree-sitter test
"""

import time
from pycparser import c_parser, c_ast
import re

print("="*70)
print("Testing Problem08_label20.c with pycparser")
print("="*70)

# Step 1: Read file
print("\n1. Reading file...")
with open('Problem08_label20.c', 'r') as f:
    source_code = f.read()

print(f"   Size: {len(source_code):,} bytes")
print(f"   Lines: {len(source_code.splitlines()):,}")

# Step 2: Preprocess (remove comments and GCC attributes)
print("\n2. Preprocessing (remove comments, GCC attributes)...")
start = time.time()
# Remove comments
code = re.sub(r'//.*?$', '', source_code, flags=re.MULTILINE)
code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
# Remove GCC attributes
code = re.sub(r'__attribute__\s*\(\(.*?\)\)', '', code, flags=re.DOTALL)
prep_time = time.time() - start
print(f"   Time: {prep_time:.4f} sec")

# Step 3: Setup parser
print("\n3. Setting up pycparser...")
parser = c_parser.CParser()

# Step 4: Parse
print("\n4. Parsing (this may take 1-5 minutes for large files)...")
start = time.time()
try:
    ast = parser.parse(code, filename='Problem08_label20.c')
    parse_time = time.time() - start
    print(f"   ✓ Success! Time: {parse_time:.2f} sec")

    # Step 5: Count branches
    print("\n5. Counting code elements...")

    counts = {
        'functions': 0,
        'if_statements': 0,
        'switch_statements': 0,
        'case_statements': 0,
        'while_loops': 0,
        'for_loops': 0
    }

    functions = []

    class CodeAnalyzer(c_ast.NodeVisitor):
        def visit_FuncDef(self, node):
            counts['functions'] += 1
            functions.append(node.decl.name)
            self.generic_visit(node)

        def visit_If(self, node):
            counts['if_statements'] += 1
            self.generic_visit(node)

        def visit_Switch(self, node):
            counts['switch_statements'] += 1
            self.generic_visit(node)

        def visit_Case(self, node):
            counts['case_statements'] += 1
            self.generic_visit(node)

        def visit_While(self, node):
            counts['while_loops'] += 1
            self.generic_visit(node)

        def visit_For(self, node):
            counts['for_loops'] += 1
            self.generic_visit(node)

    start = time.time()
    analyzer = CodeAnalyzer()
    analyzer.visit(ast)
    analysis_time = time.time() - start
    print(f"   ✓ Done! Time: {analysis_time:.2f} sec")

    # Results
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    print(f"Functions:          {counts['functions']:>10,}")
    print(f"If statements:      {counts['if_statements']:>10,}")
    print(f"Switch statements:  {counts['switch_statements']:>10,}")
    print(f"Case statements:    {counts['case_statements']:>10,}")
    print(f"While loops:        {counts['while_loops']:>10,}")
    print(f"For loops:          {counts['for_loops']:>10,}")

    print(f"\nFirst 10 functions:")
    for i, func in enumerate(functions[:10], 1):
        print(f"  {i}. {func}")

    if len(functions) > 10:
        print(f"  ... and {len(functions) - 10} more")

    # Performance
    print("\n" + "="*70)
    print("PERFORMANCE:")
    print("="*70)
    total = prep_time + parse_time + analysis_time
    print(f"Preprocessing:  {prep_time:>8.2f} sec")
    print(f"Parsing:        {parse_time:>8.2f} sec")
    print(f"Analysis:       {analysis_time:>8.2f} sec")
    print(f"{'─'*35}")
    print(f"TOTAL:          {total:>8.2f} sec")

    lines = len(source_code.splitlines())
    print(f"\nSpeed: {len(code)/parse_time/1000:.2f} thousand bytes/sec")
    print(f"Lines/sec: {lines/parse_time:,.0f}")

    print("\n" + "="*70)
    print("✓ TEST COMPLETE")
    print("="*70)

except Exception as e:
    parse_time = time.time() - start
    print(f"\n✗ PARSING FAILED")
    print(f"   Time before error: {parse_time:.2f} sec")
    print(f"   Error: {type(e).__name__}")
    print(f"   Message: {str(e)[:200]}")
    print("\n   Note: pycparser may fail or timeout on very large files.")
    print("   Consider using tree-sitter for better performance.")