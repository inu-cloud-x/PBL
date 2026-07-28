// contracts/PasskeyRegistry.sol
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice credentialId 해시 → AA 계정 주소 디렉토리.
///         완전 공개, 검열 불가, 업그레이드 불가.
contract PasskeyRegistry {
    /// @dev keccak256(credentialId) => account
    mapping(bytes32 => address) public accountOf;

    event Linked(bytes32 indexed credentialIdHash, address indexed account);

    /// @notice 호출자(=AA 계정 자신)가 자신의 credentialId 해시를 등록한다.
    ///         이미 등록된 매핑은 덮어쓸 수 없다 (탈취 방지).
    function link(bytes32 credentialIdHash) external {
        require(accountOf[credentialIdHash] == address(0), "already linked");
        accountOf[credentialIdHash] = msg.sender;
        emit Linked(credentialIdHash, msg.sender);
    }
}