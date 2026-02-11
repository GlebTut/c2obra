#!/usr/bin/env python3
"""
C Testing Coverage Tool - Source Instrumener
Iteration 1: Basic branch instrumentation  
"""

import sys
from tree_sitter import Language, Parser
import tree_sitter_c

"""Parse C source file with tree-sitter"""
def parse_c_file(filename):
    # TODO: Read file
    # TODO: Parse with tree-sitter
    # TODO: Return tree
    pass

"""Find all branch points in the AST"""
def find_branches(tree):
    branches = []
    # TODO: Walk the tree
    # TODO: Find if_statement, for_statement, while_statement, swith_statement
    # TODO: Store node positions (byte offsets)
    return branches

"""Insert __coverage_hit(id) at each branch"""
def instrument_code(source_code, branches):
    # TODO: Insert Instrumentation calls
    # TODO: Be careful with byte offsets!
    pass

def main():
    # Check command line arguments
    if len(sys.argv) != 3:
        print("Usage: python3 instrument.py <input.c> <output.c>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # TODO: Call the functions
    print(f"Instrumenting {input_file}...")
    # tree = parse_c_file(input_file)
    # branches = find_branches(tree)
    # instrumented = instrument_code(source_code, branches)
    # write output
    print(f"Done! Wrote {output_file}")

# Entry point for the instrumentation script
if __name__ == "__main__":
    main()