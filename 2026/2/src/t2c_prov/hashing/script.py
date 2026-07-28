import ast
import hashlib
import black
from typing import Dict

class NormalizeVariables(ast.NodeTransformer):
    """
    Renames variables to _v0, _v1, ... based on their order of appearance.
    Standardizes 'cadquery' as 'cq'.
    """
    def __init__(self):
        self.var_map: Dict[str, str] = {}
        self.counter = 0
        self.standard_names = {"cadquery": "cq", "cq": "cq", "result": "result"}

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, (ast.Store, ast.Load)):
            if node.id in self.standard_names:
                node.id = self.standard_names[node.id]
            elif node.id not in self.var_map:
                self.var_map[node.id] = f"_v{self.counter}"
                self.counter += 1
                node.id = self.var_map[node.id]
            else:
                node.id = self.var_map[node.id]
        return node

class StripDocstrings(ast.NodeTransformer):
    """Removes docstrings and standalone string literals from the AST."""
    def visit_Expr(self, node: ast.Expr):
        if isinstance(node.value, (ast.Str, ast.Constant)) and isinstance(node.value.value, str):
            return None
        return node
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        if (node.body and isinstance(node.body[0], ast.Expr) and 
            isinstance(node.body[0].value, (ast.Str, ast.Constant))):
            node.body.pop(0)
        self.generic_visit(node)
        return node

class DataFlowSimplifier(ast.NodeTransformer):
    """
    Simplifies redundant assignments like 'var = expr; result = var' 
    into 'result = expr'. This improves similarity matching for functionally
    identical scripts with different intermediate variable usage.
    """
    def visit_Module(self, node: ast.Module):
        self.generic_visit(node)
        
        # Simple one-pass substitution
        assignments = {}
        new_body = []
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name):
                    # If assigning to result, check if we can substitute
                    if target.id == "result" and isinstance(stmt.value, ast.Name):
                        if stmt.value.id in assignments:
                            # Remove the original assignment from new_body
                            new_body = [s for s in new_body if not (isinstance(s, ast.Assign) and len(s.targets) == 1 and getattr(s.targets[0], 'id', '') == stmt.value.id)]
                            
                            new_stmt = ast.Assign(
                                targets=[ast.Name(id="result", ctx=ast.Store())],
                                value=assignments[stmt.value.id]
                            )
                            ast.copy_location(new_stmt, stmt)
                            ast.fix_missing_locations(new_stmt)
                            new_body.append(new_stmt)
                            continue
                    # Otherwise, store the assignment for potential later substitution
                    assignments[target.id] = stmt.value
            new_body.append(stmt)
        node.body = new_body
        return node

def hash_script(code: str) -> bytes:
    """
    Generates a canonical hash of a CadQuery script.
    Functional changes result in different hashes, while stylistic changes 
    (whitespace, comments, variable names) result in the same hash.
    """
    try:
        tree = ast.parse(code)
        
        # 1. Strip docstrings (comments are stripped by ast.parse automatically)
        tree = StripDocstrings().visit(tree)
        
        # 2. Normalize variable names
        tree = NormalizeVariables().visit(tree)
        
        # 3. Convert back to code
        canonical_code = ast.unparse(tree)
        
        # 4. Standardize formatting with Black
        formatted_code = black.format_str(canonical_code, mode=black.Mode(line_length=88))
        
        # 5. Hash
        return hashlib.sha256(formatted_code.encode("utf-8")).digest()
    except Exception as e:
        # Fallback to simple hash if AST parsing fails
        # In a real system, we might want to log this failure.
        return hashlib.sha256(code.encode("utf-8")).digest()
