from web3 import Web3
from eth_account import Account
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import json
import os

class WorldStateModel(BaseModel):
    modelId: bytes
    promptHash: bytes
    scriptHash: bytes
    geometryHashA: bytes
    geometryHashB: bytes
    producer: str
    modelProvider: str
    currentOwner: str
    bloomFilterRoot: bytes
    status: int
    timestamp: int
    ipfsCid: str

    def to_solidity_tuple(self) -> tuple:
        return (
            self.modelId,
            self.promptHash,
            self.scriptHash,
            self.geometryHashA,
            self.geometryHashB,
            self.producer,
            self.modelProvider,
            self.currentOwner,
            self.bloomFilterRoot,
            self.status,
            self.timestamp,
            self.ipfsCid
        )

class RegistryClient:
    def __init__(self, rpc_url: str = "http://127.0.0.1:8545", contract_address: Optional[str] = None, abi_path: Optional[str] = None):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.contract_address = contract_address
        
        if abi_path and contract_address:
            if not os.path.exists(abi_path):
                raise FileNotFoundError(f"ABI file not found at {abi_path}")
                
            with open(abi_path, "r") as f:
                artifact = json.load(f)
                # Hardhat artifacts have 'abi' key, but sometimes raw ABI is provided
                abi = artifact["abi"] if isinstance(artifact, dict) and "abi" in artifact else artifact
            
            self.contract = self.w3.eth.contract(address=contract_address, abi=abi)
        else:
            self.contract = None
            
    def register(self, account_key: str, state: WorldStateModel) -> str:
        if not self.contract:
            raise ValueError("Contract not initialized with address and ABI")
            
        account = Account.from_key(account_key)
        
        # Estimate gas or use a safe default
        try:
            gas_estimate = self.contract.functions.register(
                state.promptHash,
                state.to_solidity_tuple()
            ).estimate_gas({"from": account.address})
            gas_limit = int(gas_estimate * 1.2) # 20% buffer
        except Exception:
            gas_limit = 500000 # Safe fallback for complex structs
            
        tx = self.contract.functions.register(
            state.promptHash,
            state.to_solidity_tuple()
        ).build_transaction({
            "from": account.address,
            "nonce": self.w3.eth.get_transaction_count(account.address),
            "gas": gas_limit,
            "gasPrice": self.w3.eth.gas_price
        })
        
        signed_tx = account.sign_transaction(tx)
        # Use raw_transaction (snake_case) for newer eth-account versions
        raw_tx = getattr(signed_tx, "raw_transaction", getattr(signed_tx, "rawTransaction", None))
        if raw_tx is None:
            raise AttributeError("Could not find raw transaction attribute on signed transaction")
            
        tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # In web3 v6, transactionHash is a HexBytes object
        if hasattr(receipt.transactionHash, "hex"):
            return receipt.transactionHash.hex()
        return str(receipt.transactionHash)

    def verify(self, prompt_hash: bytes) -> Optional[Dict[str, Any]]:
        if not self.contract:
            raise ValueError("Contract not initialized")
        
        try:
            raw_state = self.contract.functions.verify(prompt_hash).call()
            if raw_state[10] == 0: # Timestamp is 0
                return None
            return self._parse_state(raw_state)
        except Exception as e:
            print(f"Contract call failed: {e}")
            return None

    def _parse_state(self, raw: tuple) -> Dict[str, Any]:
        return {
            "modelId": raw[0],
            "promptHash": raw[1],
            "scriptHash": raw[2],
            "geometryHashA": raw[3],
            "geometryHashB": raw[4],
            "producer": raw[5],
            "modelProvider": raw[6],
            "currentOwner": raw[7],
            "bloomFilterRoot": raw[8],
            "status": raw[9],
            "timestamp": raw[10],
            "ipfsCid": raw[11]
        }
