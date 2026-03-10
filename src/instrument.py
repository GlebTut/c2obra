#!/usr/bin/env python3
"""
C Testing Coverage Tool - Source Instrumenter
Iteration 1: Basic branch instrumentation  
"""

import sys
from tree_sitter import Language, Parser
import tree_sitter_c
import json

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
        if node.type in ['if_statement', 'for_statement', 'while_statement', 'switch_statement', 'do_statement']:
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

def get_switch_cases(switch_node, source_code):
    """Extract switch expression and all case/default labels"""
    
    # Get switch expression - the (x) part
    expr = ""
    for child in switch_node.children:
        if child.type == 'parenthesized_expression':
            inner = source_code[child.start_byte:child.end_byte].decode('utf-8')
            expr = inner[1:-1].strip() # strip outer parens
            break

    # Get all case/default labels from body
    cases = []
    for child in switch_node.children:
        if child.type == 'compound_statement':
            for stmt in child.children:
                if stmt.type == 'case_statement':
                    # Check if this is actually a default: (first child is 'default' keyword)
                    first = stmt.children[0] if stmt.children else None
                    if first and first.type == 'default':
                        cases.append({'kind': 'default', 'line': stmt.start_point[0] + 1})
                        continue

                    # Normal case: grab value before ':'
                    value_node = None
                    for sub in stmt.children:
                        if sub.type == ':':
                            break
                        if sub.type not in ('case', 'comment'):
                            value_node = sub
                    if value_node is None:
                        continue
                    val = source_code[value_node.start_byte:value_node.end_byte].decode('utf-8').strip()
                    cases.append({'kind': 'case', 'value': val, 'line': stmt.start_point[0] + 1})
    return {'expression': expr, 'cases': cases}

def build_cover_chain(switch_meta, base_id):
    """Build the if/else if cover() chain to inject before switch"""
    
    expr = switch_meta['expression']
    cases = switch_meta['cases']
    lines = []
    current_id = base_id
    
    for i, case in enumerate(cases):
        prefix = "if " if i ==0 else "else if "
        
        if case['kind'] == 'case':
            condition = f"{expr} == {case['value']}"
            line = f"{prefix}(cover({condition}, {current_id})) ;"
        else:   # default
            line = f"else cover(1, {current_id});"
        
        lines.append(line)
        current_id += 1
    
    # No default? Add implict "no more case matched" branch
    has_default = any(c['kind'] == 'default' for c in cases)
    if not has_default:
        line = f"else cover(0, {current_id});"
        lines.append(line)
    
    # Join with newline + indentation for all lines after the first
    result = lines[0]
    for l in lines[1:]:
        result += "\n" + l
    return result + "\n"

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

        if branch_type in ['if_statement', 'while_statement', 'do_statement']:
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

        elif branch_type == 'switch_statement':
            switch_meta = get_switch_cases(node, source_code)
            if not switch_meta['cases']:
                continue
            
            cover_chain = build_cover_chain(switch_meta, actual_id)
            # Insert the if/else chain BEFORE the switch keyword
            insert_pos = node.start_byte
            rewriter.replace(insert_pos, insert_pos, cover_chain)

    code = rewriter.apply()
    return '#include "cov_runtime.h"\n\n' + code

def write_branch_map(branches, source_code, output_file):
    """Write branch metadata (id, line, condition) to branch_map.json"""
    sorted_branches = sorted(branches, key=lambda b: b['start_byte'])
    branch_map = []
    current_id = 1
    
    for branch in sorted_branches:
        if branch['type'] == 'switch_statement':
            meta = get_switch_cases(branch['node'], source_code)
            for case in meta['cases']:
                label = f"case {case['value']}" if case['kind'] == 'case' else 'default'
                branch_map.append({
                    "id": current_id,
                    "line": case['line'],
                    "type": "switch_case",
                    "label": label
                })
                current_id += 1
            # implicit default if no default
            if not any(c['kind'] == 'default' for c in meta['cases']):
                branch_map.append({
                    "id": current_id,
                    "line": branch['start_point'][0] + 1,
                    "type": "switch_implicit_default",
                    "label": "implicit default"
                })
                current_id += 1
        else:
            branch_map.append({
                "id": current_id,
                "line": branch['start_point'][0] + 1,
                "type": branch['type']
            })
            current_id += 1

    with open(output_file, 'w') as f:
        json.dump({"branches": branch_map}, f, indent=2)
    print(f"✓ Wrote branch map to {output_file}")
    
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
    
    map_file = output_file.replace('.c', '_branch_map.json')
    write_branch_map(branches, source_code, map_file)
    
    print(f"\nDone! Successfully instrumented {len(branches)} branches.")

# Entry point for the instrumentation script
if __name__ == "__main__":
    main()