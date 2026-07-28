// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {LibClone} from "solady/utils/LibClone.sol";
import {CoinbaseSmartWallet} from "./CoinbaseSmartWallet.sol";

/// @title Coinbase Smart Wallet Factory (non-upgradeable)
/// @notice Deploys CoinbaseSmartWallet as ERC-1167 minimal proxy (LibClone.cloneDeterministic).
///         ERC-1967 proxy removed — wallets are immutable after deployment.
contract CoinbaseSmartWalletFactory {
    address public immutable implementation;

    event AccountCreated(address indexed account, bytes[] owners, uint256 nonce);

    error ImplementationUndeployed();
    error OwnerRequired();

    constructor(address implementation_) payable {
        if (implementation_.code.length == 0) revert ImplementationUndeployed();
        implementation = implementation_;
    }

    /// @notice Deploy (or return existing) deterministic ERC-1167 clone for `owners` + `nonce`.
    function createAccount(bytes[] calldata owners, uint256 nonce)
        external
        payable
        virtual
        returns (CoinbaseSmartWallet account)
    {
        if (owners.length == 0) revert OwnerRequired();

        bytes32 salt = _getSalt(owners, nonce);
        address predicted = LibClone.predictDeterministicAddress(implementation, salt, address(this));

        if (predicted.code.length == 0) {
            // First deployment
            address deployed = LibClone.cloneDeterministic(implementation, salt);
            account = CoinbaseSmartWallet(payable(deployed));
            account.initialize{value: msg.value}(owners);
            emit AccountCreated(deployed, owners, nonce);
        } else {
            // Already deployed — return existing
            account = CoinbaseSmartWallet(payable(predicted));
            if (msg.value > 0) payable(predicted).transfer(msg.value);
        }
    }

    /// @notice Predict the address that `createAccount` would deploy.
    function getAddress(bytes[] calldata owners, uint256 nonce) external view returns (address) {
        return LibClone.predictDeterministicAddress(implementation, _getSalt(owners, nonce), address(this));
    }

    function _getSalt(bytes[] calldata owners, uint256 nonce) internal pure returns (bytes32) {
        return keccak256(abi.encode(owners, nonce));
    }
}
