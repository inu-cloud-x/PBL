// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Registry {
    enum Status { REGISTERED, CHALLENGED, REVOKED }

    struct WorldState {
        bytes32 modelId;             // Model commit SHA or ID
        bytes32 promptHash;          // SHA-256 of normalized prompt
        bytes32 scriptHash;          // CadQuery AST canonical hash
        bytes32 geometryHashA;       // Combinatorial 7-tuple
        bytes32 geometryHashB;       // FFT signature / secondary geom hash
        address producer;            // User who generated the artifact
        address modelProvider;       // Model owner/operator
        address currentOwner;        // Current owner of the artifact
        bytes32 bloomFilterRoot;     // Merkle root of off-chain bloom filter (optional)
        Status status;
        uint256 timestamp;
        string ipfsCid;              // IPFS CID of the generation bundle
    }

    // promptHash -> WorldState
    mapping(bytes32 => WorldState) public ledger;
    
    // Reverse indices for lookup
    mapping(bytes32 => bytes32[]) public scriptIndex;    // scriptHash -> promptHashes
    mapping(bytes32 => bytes32[]) public geometryIndex;  // geomHashA -> promptHashes

    event Registered(bytes32 indexed promptHash, address indexed producer, uint256 timestamp);
    event Challenged(bytes32 indexed promptHashA, bytes32 indexed promptHashB);
    event Revoked(bytes32 indexed promptHash);

    function register(
        bytes32 promptHash,
        WorldState calldata state
    ) external {
        require(ledger[promptHash].timestamp == 0, "Already registered");
        
        ledger[promptHash] = state;
        scriptIndex[state.scriptHash].push(promptHash);
        geometryIndex[state.geometryHashA].push(promptHash);
        
        emit Registered(promptHash, state.producer, block.timestamp);
    }

    function verify(bytes32 promptHash) external view returns (WorldState memory) {
        return ledger[promptHash];
    }

    function verifyByScript(bytes32 scriptHash) external view returns (bytes32[] memory) {
        return scriptIndex[scriptHash];
    }

    function verifyByGeometry(bytes32 geomHashA) external view returns (bytes32[] memory) {
        return geometryIndex[geomHashA];
    }

    function challenge(bytes32 promptHashA, bytes32 promptHashB) external {
        // Simple challenge logic for MVP
        // In reality, this would trigger an off-chain audit or ZK proof
        ledger[promptHashA].status = Status.CHALLENGED;
        ledger[promptHashB].status = Status.CHALLENGED;
        emit Challenged(promptHashA, promptHashB);
    }

    function revoke(bytes32 promptHash) external {
        // Only producer or authorized authority should be able to revoke
        // For MVP, simplified
        ledger[promptHash].status = Status.REVOKED;
        emit Revoked(promptHash);
    }
}
