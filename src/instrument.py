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

    def walk_tree(node):
        """Recursively walk the tree and find branches"""
        
        # Check if this node is a branch point
        if node.type in ['if_statement', 'for_statement', 'while_statement', 'switch_statement']:
            # Store the node info
            branches.append({
                'type': node.type,
                'node': node,
                'start_byte': node.start_byte,
                'end_byte': node.end_byte,
                'start_point': node.start_point, # (row, column)
                'end_point': node.end_point
            })
            
        # Recursively visit all children
        for child in node.children:
            walk_tree(child)
    
    # Start walking from the root
    walk_tree(tree.root_node)
    
    # Return branches
    return branches

def get_condition_node(branch_node):
    """Extract the condition node from an if/for/while statement"""
    
    for child in branch_node.children:
        if child.type == 'parenthesized_expression':
            return child
    
    return None

def instrument_code(source_code, branches):
    """Wrap branch conditions with cover() macro"""
    
    # Sort branches by position
    # Insert from END to START so offsets don't shift
    sorted_branches = sorted(branches, key=lambda b: b['start_byte'], reverse=True)
    
    # Convert bytes to string for easier manipulation
    code = source_code.decode('utf-8')
    
    # Process each branch (from end to start)
    for branch_id, branch in enumerate(sorted_branches, 1):
        branch_type = branch['type']
        node = branch['node']
        
        # ? Only handle if/else statement
        if branch_type in ['if_statement', 'while_statement']:
            # Get the condition node
            condition_node = get_condition_node(node)
            
            if condition_node:
                # Get the start and end positions
                cond_start = condition_node.start_byte
                cond_end = condition_node.end_byte
                
                # Extract the condition text
                condition_text = source_code[cond_start:cond_end].decode('utf-8')
                
                # Remove outer parentheses if present
                if condition_text.startswith('(') and condition_text.endswith(')'):
                    inner_condition = condition_text[1:-1]
                else:
                    inner_condition = condition_text
                    
                # Create the new wrapped condition
                new_condition = f"(cover({inner_condition}, {branch_id}))"
                
                # Replace in code
                code = code[:cond_start] + new_condition + code[cond_end:]
    
    # Add #include at the top of the file
    code = '#include "cov_runtime.h"\n\n' + code
    
    return code

def main():
    # Check command line arguments
    if len(sys.argv) != 3:
        print("Usage: python3 instrument.py <input.c> <output.c>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    print(f"Instrumenting {input_file}...")
    
    # Parse the file
    tree, source_code = parse_c_file(input_file)
    print(f"✓ Parsed successfully!")
    print(f"  Source size: {len(source_code)} bytes")
    
    # Find branches
    branches = find_branches(tree)
    print(f"✓ Found {len(branches)} branch points:")
    for i, branch in enumerate(branches, 1):
        line = branch['start_point'][0] + 1 # +1 because rows start at 0
        print(f"    {i}. {branch['type']} at line {line}")
    
    # Instrument the code
    instrumented_code = instrument_code(source_code, branches)
    print(f"✓ Instrumented code generated")
    
    # Write output file
    with open(output_file, 'w') as f:
        f.write(instrumented_code)
    print(f"✓ Wrote {output_file}")
    
    print(f"\nDone! Successfully instrumented {len(branches)} branches.")

# Entry point for the instrumentation script
if __name__ == "__main__":
    main()