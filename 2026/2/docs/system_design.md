# T2C-Prov System Design

## Architecture Overview
T2C-Prov is a decentralized system for tracking the provenance of AI-generated CAD artifacts. It consists of three primary layers:

1.  **Generation Layer (Python)**:
    *   **Model**: `ricemonster/qwen2.5-3B-SFT` running on Apple Silicon (MPS).
    *   **Pipeline**: Prompt -> Inference -> Cleaning -> Hashing -> Execution.
    *   **Multi-layered Hashing**:
        *   `prompt_hash`: Canonical representation of the user input.
        *   `script_hash`: AST-normalized CadQuery code (invariant to style).
        *   `geometry_hash`: Combinatorial signature of the generated B-rep (STEP).

2.  **Blockchain Layer (Ethereum/Hardhat)**:
    *   **Registry Contract**: Maintains a global ledger of `(prompt_hash -> WorldState)`.
    *   **World State**: Contains all hashes, producer address, model ID, and IPFS CID.
    *   **Indices**: Allows reverse lookup by `script_hash` or `geometry_hash`.

3.  **Storage Layer (IPFS)**:
    *   **Bundles**: Each generation is pinned as a directory containing the prompt, raw/clean scripts, STEP, STL, and metadata.

## Data Flow
1.  User provides a prompt.
2.  System generates CAD script and geometry.
3.  System computes three layers of hashes.
4.  Data bundle is uploaded to IPFS.
5.  World state is registered on the blockchain.
6.  Auditors can verify any artifact by re-hashing it and querying the registry.

## Security Considerations
*   **Determinism**: Mandatory for verification. Achieved through greedy decoding and fixed seeds.
*   **AST Normalization**: Prevents trivial bypass of provenance by renaming variables or adding comments.
*   **Geometry Signatures**: Provides a functional anchor even if the script is lost.
