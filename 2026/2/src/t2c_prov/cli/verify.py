import typer
import hashlib
from pathlib import Path
from ..hashing.prompt import hash_prompt
from ..hashing.script import hash_script
from ..hashing.geometry import combinatorial_signature
from ..chain.client import RegistryClient
from ..config import DEFAULT_CONTRACT_ADDRESS, DEFAULT_RPC_URL, PROJECT_ROOT
import json

app = typer.Typer()

@app.command()
def verify(
    prompt: str = typer.Option(None, help="Prompt to verify"),
    script: Path = typer.Option(None, help="Script file to verify"),
    step: Path = typer.Option(None, help="STEP file to verify"),
    contract: str = typer.Option(DEFAULT_CONTRACT_ADDRESS, help="Contract address"),
    rpc: str = typer.Option(DEFAULT_RPC_URL, help="RPC URL")
):
    abi_path = PROJECT_ROOT / "chain" / "artifacts" / "contracts" / "Registry.sol" / "Registry.json"
    client = RegistryClient(rpc_url=rpc, contract_address=contract, abi_path=str(abi_path))
    
    print(f"Connecting to RPC: {rpc}")
    print(f"Contract Address: {contract}")
    if not client.w3.is_connected():
        print("Error: Could not connect to RPC server.")
        return

    results = {}
    
    if prompt:
        p_hash = hash_prompt(prompt)
        print(f"Checking prompt hash: {p_hash.hex()}")
        state = client.verify(p_hash)
        if state:
            results["match_via_prompt"] = state
    
    if script and script.exists():
        with open(script, "r") as f:
            code = f.read()
        s_hash = hash_script(code)
        print(f"Checking script hash: {s_hash.hex()}")
        prompt_hashes = client.w3.eth.contract(address=client.contract_address, abi=client.contract.abi).functions.verifyByScript(s_hash).call()
        if prompt_hashes:
            results["match_via_script"] = [client.verify(ph) for ph in prompt_hashes]

    if step and step.exists():
        g_hash = combinatorial_signature(step)
        print(f"Checking geometry hash: {g_hash.hex()}")
        prompt_hashes = client.w3.eth.contract(address=client.contract_address, abi=client.contract.abi).functions.verifyByGeometry(g_hash).call()
        if prompt_hashes:
            results["match_via_geometry"] = [client.verify(ph) for ph in prompt_hashes]
    
    if results:
        print("\n[Verification Success]")
        print(json.dumps(results, indent=2, default=lambda x: x.hex() if isinstance(x, bytes) else str(x)))
    else:
        print("\n[Verification Failed] No matching records found via prompt, script, or geometry.")

if __name__ == "__main__":
    app()
