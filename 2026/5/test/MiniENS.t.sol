// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MiniENS} from "../contracts/MiniENS.sol";

contract MiniENSTest is Test {
    MiniENS ens;
    address alice = address(0xA11CE);
    address bob   = address(0xB0B);

    function setUp() public {
        ens = new MiniENS();
    }

    // ── register: success ────────────────────────────────────────────────────

    function test_register_success() public {
        vm.prank(alice);
        ens.register("alice");
        assertEq(ens.resolve("alice"), alice);
        assertEq(ens.reverseLookup(alice), "alice");
    }

    function test_register_min_length() public {
        vm.prank(alice);
        ens.register("abc");
        assertEq(ens.resolve("abc"), alice);
    }

    function test_register_max_length() public {
        // 32자
        string memory name = "abcdefghijklmnopqrstuvwxyz012345";
        vm.prank(alice);
        ens.register(name);
        assertEq(ens.resolve(name), alice);
    }

    function test_register_hyphen_in_middle_allowed() public {
        vm.prank(alice);
        ens.register("my-name");
        assertEq(ens.resolve("my-name"), alice);
    }

    function test_register_digits_allowed() public {
        vm.prank(alice);
        ens.register("abc123");
        assertEq(ens.resolve("abc123"), alice);
    }

    // ── register: reverts ────────────────────────────────────────────────────

    function test_register_duplicate_name_reverts() public {
        vm.prank(alice);
        ens.register("alice");
        vm.prank(bob);
        vm.expectRevert("name taken");
        ens.register("alice");
    }

    function test_register_already_has_name_reverts() public {
        vm.prank(alice);
        ens.register("alice");
        vm.prank(alice);
        vm.expectRevert("already has name");
        ens.register("alice2");
    }

    function test_register_too_short_reverts() public {
        vm.prank(alice);
        vm.expectRevert("length 3-32");
        ens.register("ab");
    }

    function test_register_too_long_reverts() public {
        // 33자
        vm.prank(alice);
        vm.expectRevert("length 3-32");
        ens.register("abcdefghijklmnopqrstuvwxyz0123456");
    }

    function test_register_leading_hyphen_reverts() public {
        vm.prank(alice);
        vm.expectRevert("no leading/trailing hyphen");
        ens.register("-alice");
    }

    function test_register_trailing_hyphen_reverts() public {
        vm.prank(alice);
        vm.expectRevert("no leading/trailing hyphen");
        ens.register("alice-");
    }

    function test_register_uppercase_reverts() public {
        vm.prank(alice);
        vm.expectRevert("invalid char");
        ens.register("Alice");
    }

    function test_register_space_reverts() public {
        vm.prank(alice);
        vm.expectRevert("invalid char");
        ens.register("ali ce");
    }

    function test_register_dot_reverts() public {
        vm.prank(alice);
        vm.expectRevert("invalid char");
        ens.register("ali.ce");
    }

    // ── release ───────────────────────────────────────────────────────────────

    function test_release_clears_both_mappings() public {
        vm.prank(alice);
        ens.register("alice");

        vm.prank(alice);
        ens.release();

        assertEq(ens.resolve("alice"), address(0));
        assertEq(ens.reverseLookup(alice), "");
    }

    function test_release_frees_name_for_others() public {
        vm.prank(alice);
        ens.register("alice");

        vm.prank(alice);
        ens.release();

        vm.prank(bob);
        ens.register("alice");
        assertEq(ens.resolve("alice"), bob);
    }

    function test_release_allows_reregister_same_address() public {
        vm.prank(alice);
        ens.register("alice");

        vm.prank(alice);
        ens.release();

        vm.prank(alice);
        ens.register("alice-v2");
        assertEq(ens.resolve("alice-v2"), alice);
    }

    function test_release_no_name_reverts() public {
        vm.prank(alice);
        vm.expectRevert("no name registered");
        ens.release();
    }

    // ── resolve / reverseLookup: unregistered ────────────────────────────────

    function test_resolve_unregistered_returns_zero() public view {
        assertEq(ens.resolve("nobody"), address(0));
    }

    function test_reverse_lookup_unregistered_returns_empty() public view {
        assertEq(bytes(ens.reverseLookup(alice)).length, 0);
    }

    // ── events ────────────────────────────────────────────────────────────────

    function test_register_emits_event() public {
        bytes32 expectedHash = keccak256(bytes("alice"));
        vm.prank(alice);
        vm.expectEmit(true, true, false, true);
        emit MiniENS.Registered(expectedHash, "alice", alice);
        ens.register("alice");
    }

    function test_release_emits_event() public {
        vm.prank(alice);
        ens.register("alice");

        bytes32 expectedHash = keccak256(bytes("alice"));
        vm.prank(alice);
        vm.expectEmit(true, true, false, false);
        emit MiniENS.Released(expectedHash, alice);
        ens.release();
    }
}
