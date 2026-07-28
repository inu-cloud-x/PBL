// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {VotingRegistry} from "../contracts/VotingRegistry.sol";

contract DeployVoting is Script {
    function run() external {
        vm.startBroadcast();

        VotingRegistry voting = new VotingRegistry();
        console.log("VotingRegistry      :", address(voting));

        vm.stopBroadcast();

        console.log("\n--- .env variables ---");
        console.log("VITE_VOTING_REGISTRY_ADDRESS=%s", address(voting));
    }
}
