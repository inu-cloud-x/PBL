from web3 import Web3
import json
from pathlib import Path
import os

def debug_tx():
    rpc_url = "http://127.0.0.1:8545"
    tx_hash = "afbdb1a4e2d2db70bac5263dc03e9da647d5a64e9321ab9d55e906abb30a7fa8"
    
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("Failed to connect to RPC")
        return

    receipt = w3.eth.get_transaction_receipt(tx_hash)
    print(f"Transaction Status: {'Success' if receipt.status == 1 else 'Failed'}")

    abi_path = Path("chain/artifacts/contracts/Registry.sol/Registry.json")
    with open(abi_path, "r") as f:
        artifact = json.load(f)
        abi = artifact["abi"]

    contract = w3.eth.contract(abi=abi)
    tx = w3.eth.get_transaction(tx_hash)
    decoded_input = contract.decode_function_input(tx.input)
    
    # The first element is the function object, second is a dict of arguments
    args = decoded_input[1]
    print(f"Registered Prompt Hash: {args['promptHash'].hex()}")
    
    # Also check the current block number
    print(f"Current Block: {w3.eth.block_number}")

if __name__ == "__main__":
    debug_tx()
