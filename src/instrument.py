#!/usr/bin/env python3
"""
C Testing Coverage Tool - Source Instrumenter
Iteration 1: Basic branch instrumentation  
"""

import sys
from tree_sitter import Language, Parser
import tree_sitter_c

def parse_c_file(filename):
    """Parse C source file with tree-sitter"""
    
    # Read the file as bytes
    with open(filename, 'rb') as f:
        source_code = f.read()
    
    # Create parser with C language
    C_LANGUAGE = Language(tree_sitter_c.language())
    parser = Parser(C_LANGUAGE)
    
    # Parse the source code
    tree = parser.parse(source_code)
    
    # Return tree and source_code
    return tree, source_code

def find_branches(tree):
    """Find all branch points in the AST"""
    branches = []
    # TODO: Walk the tree
    # TODO: Find if_statement, for_statement, while_statement, switch_statement
    # TODO: Store node positions (byte offsets)
    return branches

def instrument_code(source_code, branches):
    """Insert __coverage_hit(id) at each branch"""
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
    
    # Call parse_c_file
    tree, source_code = parse_c_file(input_file)
    print(f"✓ Parsed successfully!")
    print(f"  Source size: {len(source_code)} bytes")
    print(f"  Root node type: {tree.root_node.type}")
    print(f"  Root has {len(tree.root_node.children)} children")
    
    # branches = find_branches(tree)
    # instrumented = instrument_code(source_code, branches)
    # write output
    print(f"Done! Wrote {output_file}")

# Entry point for the instrumentation script
if __name__ == "__main__":
    main()