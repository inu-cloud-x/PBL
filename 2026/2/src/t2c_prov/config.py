import os
import torch
from pathlib import Path

# Base directories
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "outputs"

# Create directories if they don't exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Device configuration
def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda"
    return "cpu"

DEVICE = get_device()

# Model configuration
MODEL_ID = "ricemonster/qwen2.5-3B-SFT"
DEFAULT_SEED = 42

# Blockchain configuration
DEFAULT_RPC_URL = "http://127.0.0.1:8545"
# Default Hardhat #0 account private key
DEFAULT_PRIVATE_KEY = os.getenv("T2C_PRIVATE_KEY", "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
# Default contract address (this should be updated by the user or dynamically found)
DEFAULT_CONTRACT_ADDRESS = os.getenv("T2C_CONTRACT_ADDRESS", "0x5FbDB2315678afecb367f032d93F642f64180aa3")
