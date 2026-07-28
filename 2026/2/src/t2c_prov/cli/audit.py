import typer
from pathlib import Path
from ..audit.compare import audit_artifacts
import json

app = typer.Typer()

@app.command()
def audit(
    script_a: Path = typer.Option(..., help="First script to compare"),
    script_b: Path = typer.Option(..., help="Second script to compare"),
    step_a: Path = typer.Option(..., help="First STEP file to compare"),
    step_b: Path = typer.Option(..., help="Second STEP file to compare")
):
    """
    Advanced 4-Layer Similarity Audit for CAD artifacts.
    Compares Scripts (L1), B-rep (L2), and Mesh (L3) to produce a fused similarity score (L4).
    """
    if not all([p.exists() for p in [script_a, script_b, step_a, step_b]]):
        print("Error: One or more provided files do not exist.")
        return

    print("🔍 Starting 4-layer similarity audit...")
    
    with open(script_a, "r") as f:
        code_a = f.read()
    with open(script_b, "r") as f:
        code_b = f.read()
    
    try:
        results = audit_artifacts(code_a, code_b, step_a, step_b)
        
        print("\n--- Audit Results ---")
        print(f"L1 Script Similarity: {results['l1_script_sim']:.4f}")
        print(f"L2 B-rep Similarity:  {results['l2_brep_sim']:.4f}")
        print(f"L3 Mesh Similarity:   {results['l3_mesh_sim']:.4f}")
        print(f"----------------------")
        print(f"L4 Fused Similarity:  {results['fused_similarity']:.4f}")
        print(f"Final Status:         {results['status']}")
        
        if results['status'] == "DUPLICATE":
            print("\n🚨 Conclusion: These artifacts are likely IDENTICAL or clones. High risk of plagiarism.")
        elif results['status'] == "SIMILAR":
            print("\n📝 Conclusion: These are SIMILAR/DERIVATIVE works. Likely parameter tweaks or variations.")
        else:
            print("\n✅ Conclusion: These are DIFFERENT designs. Independent creations.")

    except Exception as e:
        print(f"Audit failed: {e}")

if __name__ == "__main__":
    app()
