// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {MiniENS} from "../contracts/MiniENS.sol";

contract DeployENS is Script {
    function run() external {
        vm.startBroadcast();

        MiniENS ens = new MiniENS();
        console.log("MiniENS             :", address(ens));

        vm.stopBroadcast();

        console.log("\n--- .env variables ---");
        console.log("VITE_MINI_ENS_ADDRESS=%s", address(ens));
    }
}
