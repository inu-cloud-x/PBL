import re
import ast

def clean_output(raw: str) -> str:
    """Extract executable CadQuery Python code from model raw output."""
    
    # 1. Extract content from markdown code blocks
    code_blocks = re.findall(r"```(?:python)?\s*(.*?)```", raw, re.DOTALL)
    if code_blocks:
        code = code_blocks[0].strip()
    else:
        # Fallback: try to find the start of the code
        # Look for the first import statement
        import_match = re.search(r"^(?:import|from)\s+\w+", raw, re.MULTILINE)
        if import_match:
            code = raw[import_match.start():].strip()
        else:
            code = raw.strip()

    # 2. Ensure essential imports
    if "import cadquery" not in code and "from cadquery" not in code:
        code = "import cadquery as cq\n" + code
    
    # Always prepend math imports to be safe, as models frequently miss specific functions (sin, cos, etc.)
    code = "from math import *\n" + code
        
    # 3. Standardize output variable to 'result'
    if "result =" not in code:
        try:
            # Try to find the last assignment to a variable that might be the model
            lines = code.splitlines()
            potential_result_var = None
            for line in reversed(lines):
                assign_match = re.match(r"^(\w+)\s*=", line.strip())
                if assign_match:
                    var_name = assign_match.group(1)
                    if var_name not in ["cq", "cadquery", "math", "np", "numpy"]:
                        potential_result_var = var_name
                        break
            
            if potential_result_var:
                code += f"\nresult = {potential_result_var}"
        except Exception:
            pass

    # 4. Remove problematic export lines that use hardcoded paths
    # We handle exporting in exporter.py
    code = re.sub(r"cq\.exporters\.export\(.*?\)", "# removed hardcoded export", code)
    code = re.sub(r"result\.val\(\)\.exportStep\(.*?\)", "# removed hardcoded export", code)

    # 5. Syntax validation (optional, for logging)
    try:
        compile(code, "<string>", "exec")
    except SyntaxError:
        pass

    return code
