// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {VotingRegistry} from "../contracts/VotingRegistry.sol";

contract VotingRegistryTest is Test {
    VotingRegistry voting;

    address alice = address(0xA11CE);
    address bob   = address(0xB0B);
    address carol = address(0xCA401);

    uint256 constant ONE_HOUR = 1 hours;
    uint256 constant ONE_DAY  = 1 days;
    uint256 constant THIRTY_DAYS = 30 days;

    function setUp() public {
        voting = new VotingRegistry();
        // Give the EVM a realistic starting timestamp
        vm.warp(1_700_000_000);
    }

    // ── helpers ───────────────────────────────────────────────────────────────

    function _create(
        address creator,
        string memory title,
        uint256 duration
    ) internal returns (uint256 id) {
        vm.prank(creator);
        voting.createProposal(title, bytes("test description"), duration);
        return voting.proposalCount() - 1;
    }

    // ── createProposal: success ───────────────────────────────────────────────

    function test_create_success() public {
        uint256 id = _create(alice, "My Proposal", ONE_HOUR);
        VotingRegistry.Proposal memory p = voting.getProposal(id);

        assertEq(p.creator, alice);
        assertEq(p.title,   "My Proposal");
        assertEq(p.deadline, uint64(block.timestamp + ONE_HOUR));
        assertEq(p.yesVotes,     0);
        assertEq(p.noVotes,      0);
        assertEq(p.abstainVotes, 0);
    }

    function test_create_increments_count() public {
        assertEq(voting.proposalCount(), 0);
        _create(alice, "First",  ONE_DAY);
        assertEq(voting.proposalCount(), 1);
        _create(bob,   "Second", ONE_DAY);
        assertEq(voting.proposalCount(), 2);
    }

    function test_create_max_title_length() public {
        bytes memory b = new bytes(100);
        for (uint i; i < 100; i++) b[i] = 0x61;
        _create(alice, string(b), ONE_DAY);
    }

    function test_create_max_description_length() public {
        bytes memory desc = new bytes(500);
        vm.prank(alice);
        voting.createProposal("Title", desc, ONE_DAY);
    }

    function test_create_min_duration() public {
        _create(alice, "Min", ONE_HOUR);
    }

    function test_create_max_duration() public {
        _create(alice, "Max", THIRTY_DAYS);
    }

    // ── createProposal: reverts ───────────────────────────────────────────────

    function test_create_empty_title_reverts() public {
        vm.prank(alice);
        vm.expectRevert("title 1-100 bytes");
        voting.createProposal("", bytes("desc"), ONE_DAY);
    }

    function test_create_title_too_long_reverts() public {
        bytes memory b = new bytes(101);
        for (uint i; i < 101; i++) b[i] = 0x61;
        vm.prank(alice);
        vm.expectRevert("title 1-100 bytes");
        voting.createProposal(string(b), bytes("desc"), ONE_DAY);
    }

    function test_create_description_too_long_reverts() public {
        bytes memory desc = new bytes(501);
        vm.prank(alice);
        vm.expectRevert("desc max 500 bytes");
        voting.createProposal("Title", desc, ONE_DAY);
    }

    function test_create_duration_too_short_reverts() public {
        vm.prank(alice);
        vm.expectRevert("invalid duration");
        voting.createProposal("Title", bytes("desc"), ONE_HOUR - 1);
    }

    function test_create_duration_too_long_reverts() public {
        vm.prank(alice);
        vm.expectRevert("invalid duration");
        voting.createProposal("Title", bytes("desc"), THIRTY_DAYS + 1);
    }

    // ── vote: success ─────────────────────────────────────────────────────────

    function test_vote_yes() public {
        uint256 id = _create(alice, "Proposal", ONE_DAY);
        vm.prank(bob);
        voting.vote(id, VotingRegistry.Choice.Yes);

        VotingRegistry.Proposal memory p = voting.getProposal(id);
        assertEq(p.yesVotes,     1);
        assertEq(p.noVotes,      0);
        assertEq(p.abstainVotes, 0);
        assertTrue(voting.hasVoted(id, bob));
    }

    function test_vote_no() public {
        uint256 id = _create(alice, "Proposal", ONE_DAY);
        vm.prank(bob);
        voting.vote(id, VotingRegistry.Choice.No);

        VotingRegistry.Proposal memory p = voting.getProposal(id);
        assertEq(p.yesVotes,     0);
        assertEq(p.noVotes,      1);
        assertEq(p.abstainVotes, 0);
    }

    function test_vote_abstain() public {
        uint256 id = _create(alice, "Proposal", ONE_DAY);
        vm.prank(bob);
        voting.vote(id, VotingRegistry.Choice.Abstain);

        VotingRegistry.Proposal memory p = voting.getProposal(id);
        assertEq(p.yesVotes,     0);
        assertEq(p.noVotes,      0);
        assertEq(p.abstainVotes, 1);
    }

    function test_vote_multiple_voters() public {
        uint256 id = _create(alice, "Proposal", ONE_DAY);
        vm.prank(alice); voting.vote(id, VotingRegistry.Choice.Yes);
        vm.prank(bob);   voting.vote(id, VotingRegistry.Choice.No);
        vm.prank(carol); voting.vote(id, VotingRegistry.Choice.Yes);

        VotingRegistry.Proposal memory p = voting.getProposal(id);
        assertEq(p.yesVotes, 2);
        assertEq(p.noVotes,  1);
    }

    // ── vote: reverts ─────────────────────────────────────────────────────────

    function test_vote_after_deadline_reverts() public {
        uint256 id = _create(alice, "Proposal", ONE_HOUR);
        vm.warp(block.timestamp + ONE_HOUR + 1);
        vm.prank(bob);
        vm.expectRevert("voting closed");
        voting.vote(id, VotingRegistry.Choice.Yes);
    }

    function test_vote_at_exact_deadline_reverts() public {
        uint256 id = _create(alice, "Proposal", ONE_HOUR);
        vm.warp(block.timestamp + ONE_HOUR); // deadline is exclusive
        vm.prank(bob);
        vm.expectRevert("voting closed");
        voting.vote(id, VotingRegistry.Choice.Yes);
    }

    function test_vote_duplicate_reverts() public {
        uint256 id = _create(alice, "Proposal", ONE_DAY);
        vm.prank(bob);
        voting.vote(id, VotingRegistry.Choice.Yes);
        vm.prank(bob);
        vm.expectRevert("already voted");
        voting.vote(id, VotingRegistry.Choice.No);
    }

    function test_vote_nonexistent_proposal_reverts() public {
        vm.prank(bob);
        vm.expectRevert("proposal not found");
        voting.vote(999, VotingRegistry.Choice.Yes);
    }

    // ── hasVoted tracking ────────────────────────────────────────────────────

    function test_has_voted_false_before_voting() public {
        uint256 id = _create(alice, "Proposal", ONE_DAY);
        assertFalse(voting.hasVoted(id, bob));
    }

    function test_has_voted_true_after_voting() public {
        uint256 id = _create(alice, "Proposal", ONE_DAY);
        vm.prank(bob);
        voting.vote(id, VotingRegistry.Choice.Abstain);
        assertTrue(voting.hasVoted(id, bob));
        assertFalse(voting.hasVoted(id, carol));
    }

    // ── events ────────────────────────────────────────────────────────────────

    function test_create_emits_event() public {
        uint64 expectedDeadline = uint64(block.timestamp + ONE_DAY);
        vm.prank(alice);
        vm.expectEmit(true, true, false, true);
        emit VotingRegistry.ProposalCreated(0, alice, "Proposal", expectedDeadline);
        voting.createProposal("Proposal", bytes("desc"), ONE_DAY);
    }

    function test_vote_emits_event() public {
        uint256 id = _create(alice, "Proposal", ONE_DAY);
        vm.prank(bob);
        vm.expectEmit(true, true, false, true);
        emit VotingRegistry.VoteCast(id, bob, VotingRegistry.Choice.Yes);
        voting.vote(id, VotingRegistry.Choice.Yes);
    }
}
