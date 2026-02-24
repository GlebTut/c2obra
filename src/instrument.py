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

def get_for_condition_node(for_node):
    """Extract the condition from a for loop"""
    
    # The condition in a for loop is typically the second child (after initialization)
    cond = for_node.child_by_field_name("condition")
    if cond is not None:
        return cond

    for child in for_node.children:
        if child.type in (
            "binary_expression",
            "identifier",
            "call_expression",
            "parenthesized_expression",
            "relational_expression",
            "logical_expression",
            "update_expression",
            "assignment_expression",
        ):
            return child
    return None                

class SourceRewriter:
    """Collects source edits and applies them safely end-to-start"""

    def __init__(self, source: bytes):
        self.source = source
        self.edits = []  # list of (start_byte, end_byte, replacement_str)

    def replace(self, start, end, text):
        self.edits.append((start, end, text))

    def apply(self):
        result = self.source
        for start, end, text in sorted(self.edits, key=lambda e: e[0], reverse=True):
            result = result[:start] + text.encode() + result[end:]
        return result.decode('utf-8')
    
def instrument_code(source_code, branches):
    """Wrap branch conditions with cover() macro"""

    total = len(branches)
    rewriter = SourceRewriter(source_code)

    for i, branch in enumerate(
        sorted(branches, key=lambda b: b['start_byte'], reverse=True), 1
    ):
        actual_id = total - i + 1
        branch_type = branch['type']
        node = branch['node']

        if branch_type in ['if_statement', 'while_statement']:
            condition_node = get_condition_node(node)
            if condition_node:
                cond_start = condition_node.start_byte
                cond_end = condition_node.end_byte
                condition_text = source_code[cond_start:cond_end].decode('utf-8')

                if condition_text.startswith('(') and condition_text.endswith(')'):
                    inner = condition_text[1:-1]
                else:
                    inner = condition_text

                rewriter.replace(cond_start, cond_end, f"(cover({inner}, {actual_id}))")

        elif branch_type == 'for_statement':
            condition_node = get_for_condition_node(node)
            if condition_node:
                cond_start = condition_node.start_byte
                cond_end = condition_node.end_byte
                condition_text = source_code[cond_start:cond_end].decode('utf-8').strip()
                if condition_text:
                    rewriter.replace(cond_start, cond_end, f" cover({condition_text}, {actual_id}) ")

    code = rewriter.apply()
    return '#include "cov_runtime.h"\n\n' + code

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