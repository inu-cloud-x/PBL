# World State Schema (Registry.sol)

The `WorldState` struct is the core data unit stored on the blockchain.

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `modelId` | `bytes32` | Commit SHA of the `ricemonster/qwen2.5-3B-SFT` model. |
| `promptHash` | `bytes32` | SHA-256 of the NFKC-normalized, lowercase prompt. |
| `scriptHash` | `bytes32` | SHA-256 of the AST-normalized, Black-formatted CadQuery code. |
| `geometryHashA`| `bytes32` | Combinatorial 7-tuple (Faces, Edges, Verts, Area, Volume, AR_X, AR_Y). |
| `geometryHashB`| `bytes32` | Secondary geometric signature (e.g., moments of inertia or FFT). |
| `producer` | `address` | The Ethereum address of the user who initiated the generation. |
| `modelProvider`| `address` | The address of the entity providing the model inference. |
| `currentOwner` | `address` | The current owner of the artifact (transferable). |
| `bloomFilterRoot`| `bytes32` | Merkle root for efficient off-chain membership proofs. |
| `status` | `uint8` | Status enum: `0: REGISTERED`, `1: CHALLENGED`, `2: REVOKED`. |
| `timestamp` | `uint256` | Block timestamp of the registration. |
| `ipfsCid` | `string` | The IPFS CID pointing to the full generation bundle. |

## Indices
*   `ledger`: Primary mapping of `promptHash` to `WorldState`.
*   `scriptIndex`: Reverse mapping from `scriptHash` to a list of `promptHash`es.
*   `geometryIndex`: Reverse mapping from `geometryHashA` to a list of `promptHash`es.
