// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IAccount} from "account-abstraction/interfaces/IAccount.sol";
import {UserOperation, UserOperationLib} from "account-abstraction/interfaces/UserOperation.sol";
import {Receiver} from "solady/accounts/Receiver.sol";
import {SignatureCheckerLib} from "solady/utils/SignatureCheckerLib.sol";
import {WebAuthn} from "webauthn-sol/WebAuthn.sol";

import {ERC1271} from "./ERC1271.sol";
import {MultiOwnable} from "./MultiOwnable.sol";

/// @title Coinbase Smart Wallet (non-upgradeable)
/// @notice ERC-4337 EP v0.6 smart account. UUPS upgrade logic removed.
///         Deployed as an ERC-1167 minimal proxy via CoinbaseSmartWalletFactory.
contract CoinbaseSmartWallet is ERC1271, IAccount, MultiOwnable, Receiver {
    struct SignatureWrapper {
        uint256 ownerIndex;
        bytes signatureData;
    }

    struct Call {
        address target;
        uint256 value;
        bytes data;
    }

    uint256 public constant REPLAYABLE_NONCE_KEY = 8453;

    error Initialized();
    error SelectorNotAllowed(bytes4 selector);
    error InvalidNonceKey(uint256 key);

    modifier onlyEntryPoint() virtual {
        if (msg.sender != entryPoint()) revert Unauthorized();
        _;
    }

    modifier onlyEntryPointOrOwner() virtual {
        if (msg.sender != entryPoint()) _checkOwner();
        _;
    }

    modifier payPrefund(uint256 missingAccountFunds) virtual {
        _;
        assembly ("memory-safe") {
            if missingAccountFunds {
                pop(call(gas(), caller(), missingAccountFunds, codesize(), 0x00, codesize(), 0x00))
            }
        }
    }

    constructor() {
        // Lock implementation — proxies use their own storage.
        bytes[] memory owners = new bytes[](1);
        owners[0] = abi.encode(address(0));
        _initializeOwners(owners);
    }

    function initialize(bytes[] calldata owners) external payable virtual {
        if (nextOwnerIndex() != 0) revert Initialized();
        _initializeOwners(owners);
    }

    /// @inheritdoc IAccount
    function validateUserOp(UserOperation calldata userOp, bytes32 userOpHash, uint256 missingAccountFunds)
        external
        virtual
        onlyEntryPoint
        payPrefund(missingAccountFunds)
        returns (uint256 validationData)
    {
        uint256 key = userOp.nonce >> 64;

        if (bytes4(userOp.callData) == this.executeWithoutChainIdValidation.selector) {
            userOpHash = getUserOpHashWithoutChainId(userOp);
            if (key != REPLAYABLE_NONCE_KEY) revert InvalidNonceKey(key);
        } else {
            if (key == REPLAYABLE_NONCE_KEY) revert InvalidNonceKey(key);
        }

        return _isValidSignature(userOpHash, userOp.signature) ? 0 : 1;
    }

    function executeWithoutChainIdValidation(bytes[] calldata calls) external payable virtual onlyEntryPoint {
        for (uint256 i; i < calls.length; i++) {
            bytes4 selector = bytes4(calls[i]);
            if (!canSkipChainIdValidation(selector)) revert SelectorNotAllowed(selector);
            _call(address(this), 0, calls[i]);
        }
    }

    function execute(address target, uint256 value, bytes calldata data)
        external payable virtual onlyEntryPointOrOwner
    {
        _call(target, value, data);
    }

    function executeBatch(Call[] calldata calls) external payable virtual onlyEntryPointOrOwner {
        for (uint256 i; i < calls.length; i++) {
            _call(calls[i].target, calls[i].value, calls[i].data);
        }
    }

    /// @notice EntryPoint v0.6
    function entryPoint() public view virtual returns (address) {
        return 0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789;
    }

    function getUserOpHashWithoutChainId(UserOperation calldata userOp) public view virtual returns (bytes32) {
        return keccak256(abi.encode(UserOperationLib.hash(userOp), entryPoint()));
    }

    function canSkipChainIdValidation(bytes4 sel) public pure returns (bool) {
        return sel == MultiOwnable.addOwnerPublicKey.selector
            || sel == MultiOwnable.addOwnerAddress.selector
            || sel == MultiOwnable.removeOwnerAtIndex.selector
            || sel == MultiOwnable.removeLastOwner.selector;
    }

    function _call(address target, uint256 value, bytes memory data) internal {
        (bool success, bytes memory result) = target.call{value: value}(data);
        if (!success) {
            assembly ("memory-safe") {
                revert(add(result, 32), mload(result))
            }
        }
    }

    function _isValidSignature(bytes32 hash, bytes calldata signature)
        internal view virtual override returns (bool)
    {
        SignatureWrapper memory sigWrapper = abi.decode(signature, (SignatureWrapper));
        bytes memory ownerBytes = ownerAtIndex(sigWrapper.ownerIndex);

        if (ownerBytes.length == 32) {
            if (uint256(bytes32(ownerBytes)) > type(uint160).max) revert InvalidEthereumAddressOwner(ownerBytes);
            address owner;
            assembly ("memory-safe") { owner := mload(add(ownerBytes, 32)) }
            return SignatureCheckerLib.isValidSignatureNow(owner, hash, sigWrapper.signatureData);
        }

        if (ownerBytes.length == 64) {
            (uint256 x, uint256 y) = abi.decode(ownerBytes, (uint256, uint256));
            WebAuthn.WebAuthnAuth memory auth = abi.decode(sigWrapper.signatureData, (WebAuthn.WebAuthnAuth));
            return WebAuthn.verify({challenge: abi.encode(hash), requireUV: false, webAuthnAuth: auth, x: x, y: y});
        }

        revert InvalidOwnerBytesLength(ownerBytes);
    }

    function _domainNameAndVersion() internal pure override returns (string memory, string memory) {
        return ("Coinbase Smart Wallet", "1");
    }
}
