import time
import csv
from pathlib import Path
from t2c_prov.generation.text_to_cadquery_runner import TextToCadQueryRunner
from t2c_prov.generation.cleaner import clean_output
from t2c_prov.hashing.script import hash_script
from t2c_prov.hashing.geometry import combinatorial_signature
from t2c_prov.generation.exporter import execute_and_export

PROMPTS = [
    "a simple cube with side length 10mm",
    "a hollow cylinder with radius 5mm, height 20mm and thickness 1mm",
    "a sphere with radius 15mm",
    "a rectangular plate 100x50mm with a hole of 10mm in the center",
    "a hexagonal nut for M8 bolt"
]

def run_g1_determinism(iterations=5):
    runner = TextToCadQueryRunner()
    results = []
    
    output_base = Path("data/eval/g1")
    output_base.mkdir(parents=True, exist_ok=True)

    for i, prompt in enumerate(PROMPTS):
        print(f"Evaluating G1 for prompt: {prompt}")
        script_hashes = []
        geom_hashes = []
        
        for j in range(iterations):
            seed = 42 # Fixed seed
            raw = runner.generate(prompt, seed=seed)
            clean = clean_output(raw)
            s_hash = hash_script(clean).hex()
            script_hashes.append(s_hash)
            
            # Export to get geometry hash
            gen_dir = output_base / f"prompt_{i}_iter_{j}"
            exec_res = execute_and_export(clean, gen_dir)
            if exec_res.success:
                g_hash = combinatorial_signature(exec_res.step_path).hex()
                geom_hashes.append(g_hash)
            else:
                geom_hashes.append("failed")

        # Calculate collision rates
        s_collision = len(set(script_hashes)) == 1
        g_collision = len(set(geom_hashes)) == 1
        
        results.append({
            "prompt": prompt,
            "script_consistent": s_collision,
            "geom_consistent": g_collision,
            "script_hashes": script_hashes,
            "geom_hashes": geom_hashes
        })

    # Save results
    with open(output_base / "results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["prompt", "script_consistent", "geom_consistent"])
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in ["prompt", "script_consistent", "geom_consistent"]})

    print(f"G1 Evaluation complete. Results saved to {output_base / 'results.csv'}")

if __name__ == "__main__":
    run_g1_determinism()
