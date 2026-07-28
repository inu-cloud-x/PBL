import cadquery as cq
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class ExecutionResult:
    success: bool
    error: Optional[str] = None
    step_path: Optional[Path] = None
    stl_path: Optional[Path] = None

def execute_and_export(script: str, out_dir: Path) -> ExecutionResult:
    """Execute CadQuery script and export to STEP and STL."""
    out_dir.mkdir(parents=True, exist_ok=True)
    
    namespace = {}
    # Security note: exec() is used here as per MVP plan. 
    # Production should use a sandbox.
    try:
        exec(script, namespace)
    except Exception as e:
        return ExecutionResult(success=False, error=f"Execution error: {str(e)}")
    
    result = namespace.get("result")
    if result is None:
        # Try to find any Workplane object if 'result' is missing
        for val in namespace.values():
            if isinstance(val, cq.Workplane):
                result = val
                break
                
    if result is None:
        return ExecutionResult(success=False, error="No CadQuery Workplane object found in namespace (expected 'result' variable)")
    
    step_path = out_dir / "model.step"
    stl_path = out_dir / "model.stl"
    
    try:
        # Export STEP
        if hasattr(result, "val"):
            result.val().exportStep(str(step_path))
        else:
            # Handle cases where result might be a list or other CQ object
            cq.exporters.export(result, str(step_path), exportType="STEP")
            
        # Export STL
        cq.exporters.export(result, str(stl_path), exportType="STL")
        
        return ExecutionResult(success=True, step_path=step_path, stl_path=stl_path)
    except Exception as e:
        return ExecutionResult(success=False, error=f"Export error: {str(e)}")
