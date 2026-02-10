#!/usr/bin/env python3
"""
Simple tree-sitter test for Problem08_label20.c
"""

import time
from tree_sitter import Language, Parser
import tree_sitter_c

print("="*70)
print("Testing Problem08_label20.c with tree-sitter")
print("="*70)

# Step 1: Read file
print("\n1. Reading file...")
with open('Problem08_label20.c', 'rb') as f:
    source_code = f.read()

print(f"   Size: {len(source_code):,} bytes")
print(f"   Lines: {source_code.count(b'\n'):,}")

# Step 2: Setup parser
print("\n2. Setting up tree-sitter parser...")
start = time.time()
C_LANGUAGE = Language(tree_sitter_c.language())
parser = Parser(C_LANGUAGE)
setup_time = time.time() - start
print(f"   Time: {setup_time:.4f} sec")

# Step 3: Parse
print("\n3. Parsing...")
start = time.time()
tree = parser.parse(source_code)
parse_time = time.time() - start
print(f"   ✓ Success! Time: {parse_time:.2f} sec")

# Step 4: Count branches
print("\n4. Counting code elements...")

counts = {
    'functions': 0,
    'if_statements': 0,
    'switch_statements': 0,
    'case_statements': 0,
    'while_loops': 0,
    'for_loops': 0
}

def count_node(node):
    """Recursively count nodes"""
    if node.type == 'function_definition':
        counts['functions'] += 1
    elif node.type == 'if_statement':
        counts['if_statements'] += 1
    elif node.type == 'switch_statement':
        counts['switch_statements'] += 1
    elif node.type == 'case_statement':
        counts['case_statements'] += 1
    elif node.type == 'while_statement':
        counts['while_loops'] += 1
    elif node.type == 'for_statement':
        counts['for_loops'] += 1

    for child in node.children:
        count_node(child)

start = time.time()
count_node(tree.root_node)
analysis_time = time.time() - start
print(f"   ✓ Done! Time: {analysis_time:.2f} sec")

# Step 5: Get function names
print("\n5. Extracting function names...")

functions = []

def get_functions(node):
    """Extract function names"""
    if node.type == 'function_definition':
        for child in node.children:
            if child.type == 'function_declarator':
                for subchild in child.children:
                    if subchild.type == 'identifier':
                        name = source_code[subchild.start_byte:subchild.end_byte].decode('utf-8')
                        functions.append(name)
                        break

    for child in node.children:
        get_functions(child)

get_functions(tree.root_node)

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
total = parse_time + analysis_time
print(f"Parsing:        {parse_time:>8.2f} sec")
print(f"Analysis:       {analysis_time:>8.2f} sec")
print(f"{'─'*35}")
print(f"TOTAL:          {total:>8.2f} sec")

lines = source_code.count(b'\n')
print(f"\nSpeed: {len(source_code)/parse_time/1000:.2f} thousand bytes/sec")
print(f"Lines/sec: {lines/parse_time:,.0f}")

print("\n" + "="*70)
print("✓ TEST COMPLETE")
print("="*70)