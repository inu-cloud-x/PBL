// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";

import {PasskeyRegistry} from "../contracts/PasskeyRegistry.sol";
import {CoinbaseSmartWallet} from "../contracts/coinbase/CoinbaseSmartWallet.sol";
import {CoinbaseSmartWalletFactory} from "../contracts/coinbase/CoinbaseSmartWalletFactory.sol";
import {DataStore} from "../contracts/DataStore.sol";

/// @notice Deploy order:
///   1. PasskeyRegistry
///   2. CoinbaseSmartWallet implementation
///   3. CoinbaseSmartWalletFactory
///   4. DataStore
contract Deploy is Script {
    function run() external {
        vm.startBroadcast();

        // 1. PasskeyRegistry
        PasskeyRegistry registry = new PasskeyRegistry();
        console.log("PasskeyRegistry     :", address(registry));

        // 2. SmartWallet implementation (constructor locks it from direct init)
        CoinbaseSmartWallet impl = new CoinbaseSmartWallet();
        console.log("SmartWallet impl    :", address(impl));

        // 3. Factory — takes the implementation address
        CoinbaseSmartWalletFactory factory = new CoinbaseSmartWalletFactory(address(impl));
        console.log("SmartWallet factory :", address(factory));

        // 4. DataStore
        DataStore store = new DataStore();
        console.log("DataStore           :", address(store));

        vm.stopBroadcast();

        console.log("\n--- .env variables ---");
        console.log("VITE_PASSKEY_REGISTRY_ADDRESS=%s", address(registry));
        console.log("VITE_SMART_WALLET_IMPL=%s",        address(impl));
        console.log("VITE_SMART_WALLET_FACTORY=%s",     address(factory));
        console.log("VITE_DATA_STORE_ADDRESS=%s",       address(store));
    }
}
