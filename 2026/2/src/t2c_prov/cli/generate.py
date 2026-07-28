import typer
from pathlib import Path
from ..generation.text_to_cadquery_runner import TextToCadQueryRunner
from ..generation.cleaner import clean_output
from ..generation.exporter import execute_and_export
from ..config import (
    OUTPUT_DIR, DEFAULT_SEED, MODEL_ID, 
    DEFAULT_RPC_URL, DEFAULT_PRIVATE_KEY, DEFAULT_CONTRACT_ADDRESS,
    PROJECT_ROOT
)
from ..hashing.prompt import hash_prompt
from ..hashing.script import hash_script
from ..hashing.geometry import combinatorial_signature
from ..storage.ipfs_client import IPFSClient
from ..chain.client import RegistryClient, WorldStateModel
import time
import os

app = typer.Typer()

def parse_model_id(sha: str) -> bytes:
    """Safely parse a SHA string into 32 bytes."""
    if not sha or sha == "unknown":
        return b"\x00" * 32
    try:
        # If it's a hex string (common for SHAs)
        clean_sha = sha.replace("0x", "")
        if len(clean_sha) > 64:
            clean_sha = clean_sha[:64]
        return bytes.fromhex(clean_sha).rjust(32, b"\x00")
    except Exception:
        # Fallback: hash the string itself if it's not hex
        import hashlib
        return hashlib.sha256(sha.encode()).digest()

@app.command()
def generate(
    prompt: str = typer.Option(..., help="Prompt for CAD generation"),
    seed: int = typer.Option(DEFAULT_SEED, help="Random seed for determinism"),
    output: Path = typer.Option(OUTPUT_DIR, help="Output directory"),
    max_tokens: int = typer.Option(512, help="Max new tokens to generate"),
    register: bool = typer.Option(False, "--register", help="Register on blockchain"),
    contract: str = typer.Option(DEFAULT_CONTRACT_ADDRESS, help="Contract address"),
    rpc: str = typer.Option(DEFAULT_RPC_URL, help="RPC URL"),
    key: str = typer.Option(DEFAULT_PRIVATE_KEY, help="Private key for registration")
):
    start_time = time.time()
    
    # 1. Initialize runner
    try:
        runner = TextToCadQueryRunner()
    except Exception as e:
        print(f"Failed to initialize model: {e}")
        return
    
    # 2. Generate raw output
    print(f"Generating CAD for: '{prompt}' (seed={seed})...")
    raw_output = runner.generate(prompt, seed=seed, max_new_tokens=max_tokens)
    checkpoint_sha = getattr(runner, "checkpoint_sha", "unknown")
    
    # 3. Clean output
    cleaned_code = clean_output(raw_output)
    
    # 4. Save scripts and metadata
    timestamp = int(time.time())
    gen_id = f"gen_{timestamp}"
    gen_dir = output / gen_id
    gen_dir.mkdir(parents=True, exist_ok=True)
    
    with open(gen_dir / "script_raw.py", "w") as f:
        f.write(raw_output)
    
    with open(gen_dir / "script.py", "w") as f:
        f.write(cleaned_code)
        
    with open(gen_dir / "prompt.txt", "w") as f:
        f.write(prompt)
        
    # 5. Execute and Export
    print("Executing and exporting geometry...")
    exec_result = execute_and_export(cleaned_code, gen_dir)
    
    if not exec_result.success:
        print(f"Generation failed during execution: {exec_result.error}")
        # We still have the scripts saved for debugging
        return

    # 6. Hashing
    print("Calculating multi-layer hashes...")
    p_hash = hash_prompt(prompt)
    s_hash = hash_script(cleaned_code)
    g_hash_a = combinatorial_signature(exec_result.step_path)
    g_hash_b = b"\x00" * 32 # Reserved for secondary geom hash (FFT)
    
    duration = time.time() - start_time
    print(f"Successfully generated CAD in {duration:.2f}s")
    print(f"Outputs saved to: {gen_dir}")

    # 7. Blockchain Registration & IPFS
    if register:
        if not contract or not key:
            print("Error: --contract and --key are required for registration.")
            return

        try:
            # IPFS Upload
            print("Uploading to IPFS...")
            ipfs = IPFSClient()
            if not ipfs.is_connected:
                raise ConnectionError("IPFS daemon connection failed. Registration aborted.")
            
            cid = ipfs.pin_directory(gen_dir)
            print(f"IPFS CID: {cid}")

            # Blockchain Registration
            print("Registering on-chain...")
            # Use absolute path for ABI to avoid location issues
            abi_path = PROJECT_ROOT / "chain" / "artifacts" / "contracts" / "Registry.sol" / "Registry.json"
            
            client = RegistryClient(rpc_url=rpc, contract_address=contract, abi_path=str(abi_path))
            
            from eth_account import Account
            account = Account.from_key(key)
            
            model_id_bytes = parse_model_id(checkpoint_sha)

            state = WorldStateModel(
                modelId=model_id_bytes,
                promptHash=p_hash,
                scriptHash=s_hash,
                geometryHashA=g_hash_a,
                geometryHashB=g_hash_b,
                producer=account.address,
                modelProvider=account.address, 
                currentOwner=account.address,
                bloomFilterRoot=b"\x00" * 32,
                status=0, # REGISTERED
                timestamp=timestamp,
                ipfsCid=cid
            )
            
            tx_hash = client.register(key, state)
            print(f"Successfully registered on-chain!")
            print(f"Transaction Hash: {tx_hash}")
            
        except Exception as e:
            print(f"Registration failed: {str(e)}")
        
if __name__ == "__main__":
    app()
