// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {VCRegistry} from "../contracts/VCRegistry.sol";

contract DeployVC is Script {
    function run() external {
        address ensAddr = vm.envAddress("VITE_MINI_ENS_ADDRESS");

        vm.startBroadcast();

        VCRegistry registry = new VCRegistry(ensAddr);
        console.log("VCRegistry           :", address(registry));

        vm.stopBroadcast();

        console.log("\n--- .env variables ---");
        console.log("VITE_VC_REGISTRY_ADDRESS=%s", address(registry));
    }
}
