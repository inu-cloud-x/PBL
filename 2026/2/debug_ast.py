import ast
from t2c_prov.hashing.script import DataFlowSimplifier, NormalizeVariables

code_a = """import cadquery as cq
result = cq.Workplane("XY").box(10, 10, 10)"""

code_b = """import cadquery as cq
my_box = cq.Workplane("XY").box(10, 10, 10)
result = my_box"""

tree_a = ast.parse(code_a)
tree_a = DataFlowSimplifier().visit(tree_a)
tree_a = NormalizeVariables().visit(tree_a)

tree_b = ast.parse(code_b)
tree_b = DataFlowSimplifier().visit(tree_b)
tree_b = NormalizeVariables().visit(tree_b)

print("--- A ---")
print(ast.unparse(tree_a))
print("--- B ---")
print(ast.unparse(tree_b))
