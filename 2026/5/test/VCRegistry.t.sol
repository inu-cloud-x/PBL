// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {VCRegistry} from "../contracts/VCRegistry.sol";

// ── Mock ENS ─────────────────────────────────────────────────────────────────

contract MockENS {
    mapping(address => string) private _names;

    function setName(address addr, string memory name) external {
        _names[addr] = name;
    }

    function reverseLookup(address addr) external view returns (string memory) {
        return _names[addr];
    }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

contract VCRegistryTest is Test {
    VCRegistry vc;
    MockENS    mockEns;

    address issuer    = address(0x1111);
    address requester = address(0x2222);
    address stranger  = address(0x3333);

    function setUp() public {
        mockEns = new MockENS();
        vc = new VCRegistry(address(mockEns));
        vm.warp(1_700_000_000);

        // Give issuer an ENS name
        mockEns.setName(issuer, "alice");
    }

    // ── registerFormat ────────────────────────────────────────────────────────

    function test_registerFormat_success() public {
        vm.prank(issuer);
        uint256 id = vc.registerFormat("MembershipVC");

        VCRegistry.Format memory f = vc.getFormat(id);
        assertEq(f.id,     0);
        assertEq(f.issuer, issuer);
        assertEq(f.name,   "MembershipVC");
        assertTrue(f.active);
        assertEq(f.createdAt, uint64(block.timestamp));
    }

    function test_registerFormat_without_ens_reverts() public {
        // stranger has no ENS name
        vm.prank(stranger);
        vm.expectRevert("ENS name required");
        vc.registerFormat("BadVC");
    }

    function test_registerFormat_empty_name_reverts() public {
        vm.prank(issuer);
        vm.expectRevert("name 1-40 bytes");
        vc.registerFormat("");
    }

    function test_registerFormat_name_too_long_reverts() public {
        bytes memory b = new bytes(41);
        for (uint i; i < 41; i++) b[i] = 0x61;
        vm.prank(issuer);
        vm.expectRevert("name 1-40 bytes");
        vc.registerFormat(string(b));
    }

    function test_registerFormat_increments_count() public {
        assertEq(vc.formatCount(), 0);
        vm.prank(issuer);
        vc.registerFormat("VC-A");
        assertEq(vc.formatCount(), 1);
        vm.prank(issuer);
        vc.registerFormat("VC-B");
        assertEq(vc.formatCount(), 2);
    }

    function test_registerFormat_emits_event() public {
        vm.prank(issuer);
        vm.expectEmit(true, true, false, true);
        emit VCRegistry.FormatRegistered(0, issuer, "MemberVC");
        vc.registerFormat("MemberVC");
    }

    // ── deactivateFormat ──────────────────────────────────────────────────────

    function test_deactivateFormat_success() public {
        vm.prank(issuer);
        uint256 id = vc.registerFormat("MemberVC");

        vm.prank(issuer);
        vc.deactivateFormat(id);

        VCRegistry.Format memory f = vc.getFormat(id);
        assertFalse(f.active);
    }

    function test_deactivate_non_issuer_reverts() public {
        vm.prank(issuer);
        uint256 id = vc.registerFormat("MemberVC");

        vm.prank(stranger);
        vm.expectRevert("not issuer");
        vc.deactivateFormat(id);
    }

    function test_deactivate_already_inactive_reverts() public {
        vm.prank(issuer);
        uint256 id = vc.registerFormat("MemberVC");
        vm.prank(issuer);
        vc.deactivateFormat(id);

        vm.prank(issuer);
        vm.expectRevert("already inactive");
        vc.deactivateFormat(id);
    }

    // ── requestVc ────────────────────────────────────────────────────────────

    function _registerAndRequest() internal returns (uint256 formatId, uint256 requestId) {
        vm.prank(issuer);
        formatId = vc.registerFormat("MemberVC");

        vm.prank(requester);
        requestId = vc.requestVc(formatId, "did:key:zABC123");
    }

    function test_requestVc_success() public {
        (uint256 fId, uint256 rId) = _registerAndRequest();

        VCRegistry.Request[] memory reqs = vc.getRequestsByRequester(requester);
        assertEq(reqs.length,     1);
        assertEq(reqs[0].id,      rId);
        assertEq(reqs[0].formatId, fId);
        assertEq(reqs[0].requester, requester);
        assertEq(reqs[0].subjectDid, "did:key:zABC123");
        assertEq(uint8(reqs[0].status), uint8(VCRegistry.Status.Pending));
    }

    function test_requestVc_inactive_format_reverts() public {
        vm.prank(issuer);
        uint256 fId = vc.registerFormat("MemberVC");
        vm.prank(issuer);
        vc.deactivateFormat(fId);

        vm.prank(requester);
        vm.expectRevert("format inactive");
        vc.requestVc(fId, "did:key:z123");
    }

    function test_requestVc_nonexistent_format_reverts() public {
        vm.prank(requester);
        vm.expectRevert("format not found");
        vc.requestVc(999, "did:key:z123");
    }

    function test_requestVc_did_too_long_reverts() public {
        vm.prank(issuer);
        uint256 fId = vc.registerFormat("MemberVC");

        bytes memory b = new bytes(201);
        for (uint i; i < 201; i++) b[i] = 0x61;

        vm.prank(requester);
        vm.expectRevert("subjectDid too long");
        vc.requestVc(fId, string(b));
    }

    // ── register → request → approve full flow ────────────────────────────────

    function test_full_approve_flow() public {
        (uint256 fId, uint256 rId) = _registerAndRequest();

        bytes32 hash = keccak256("some-vc-json");
        vm.prank(issuer);
        uint256 issuedId = vc.approveRequest(rId, "Approved member", hash);

        // Request status updated
        VCRegistry.Request[] memory reqs = vc.getRequestsByRequester(requester);
        assertEq(uint8(reqs[0].status), uint8(VCRegistry.Status.Approved));

        // Issued record created
        VCRegistry.Issued[] memory issued = vc.getIssuedToSubject(requester);
        assertEq(issued.length,    1);
        assertEq(issued[0].id,     issuedId);
        assertEq(issued[0].formatId, fId);
        assertEq(issued[0].issuer,   issuer);
        assertEq(issued[0].subject,  requester);
        assertEq(issued[0].details,  "Approved member");
        assertEq(issued[0].jsonHash, hash);
        assertEq(issued[0].expiresAt, issued[0].issuedAt + uint64(365 days));
    }

    function test_approve_sets_correct_expiry() public {
        (, uint256 rId) = _registerAndRequest();
        bytes32 hash = keccak256("vc-json");
        vm.prank(issuer);
        vc.approveRequest(rId, "details", hash);

        VCRegistry.Issued[] memory issued = vc.getIssuedToSubject(requester);
        assertEq(issued[0].expiresAt, uint64(block.timestamp) + uint64(365 days));
    }

    function test_approve_non_issuer_reverts() public {
        (, uint256 rId) = _registerAndRequest();

        vm.prank(stranger);
        vm.expectRevert("not issuer");
        vc.approveRequest(rId, "details", keccak256("hash"));
    }

    function test_approve_empty_details_reverts() public {
        (, uint256 rId) = _registerAndRequest();

        vm.prank(issuer);
        vm.expectRevert("details 1-100 bytes");
        vc.approveRequest(rId, "", keccak256("hash"));
    }

    function test_approve_details_too_long_reverts() public {
        (, uint256 rId) = _registerAndRequest();

        bytes memory b = new bytes(101);
        for (uint i; i < 101; i++) b[i] = 0x61;

        vm.prank(issuer);
        vm.expectRevert("details 1-100 bytes");
        vc.approveRequest(rId, string(b), keccak256("hash"));
    }

    function test_approve_zero_hash_reverts() public {
        (, uint256 rId) = _registerAndRequest();

        vm.prank(issuer);
        vm.expectRevert("hash required");
        vc.approveRequest(rId, "details", bytes32(0));
    }

    // ── reject flow ───────────────────────────────────────────────────────────

    function test_reject_success() public {
        (, uint256 rId) = _registerAndRequest();

        vm.prank(issuer);
        vc.rejectRequest(rId);

        VCRegistry.Request[] memory reqs = vc.getRequestsByRequester(requester);
        assertEq(uint8(reqs[0].status), uint8(VCRegistry.Status.Rejected));
    }

    function test_reject_non_pending_reverts() public {
        (, uint256 rId) = _registerAndRequest();
        vm.prank(issuer);
        vc.rejectRequest(rId);

        // Attempt to reject again
        vm.prank(issuer);
        vm.expectRevert("not pending");
        vc.rejectRequest(rId);
    }

    function test_approve_after_reject_reverts() public {
        (, uint256 rId) = _registerAndRequest();
        vm.prank(issuer);
        vc.rejectRequest(rId);

        vm.prank(issuer);
        vm.expectRevert("not pending");
        vc.approveRequest(rId, "details", keccak256("hash"));
    }

    function test_reject_non_issuer_reverts() public {
        (, uint256 rId) = _registerAndRequest();

        vm.prank(stranger);
        vm.expectRevert("not issuer");
        vc.rejectRequest(rId);
    }

    // ── deactivated format: new requests blocked, issued still visible ─────────

    function test_deactivated_format_blocks_new_requests() public {
        vm.prank(issuer);
        uint256 fId = vc.registerFormat("MemberVC");
        vm.prank(issuer);
        vc.deactivateFormat(fId);

        vm.prank(requester);
        vm.expectRevert("format inactive");
        vc.requestVc(fId, "did:key:z123");
    }

    function test_deactivated_format_existing_issued_still_visible() public {
        // Register, request, approve while still active
        (uint256 fId, uint256 rId) = _registerAndRequest();
        vm.prank(issuer);
        vc.approveRequest(rId, "member", keccak256("vc"));

        // Deactivate after issuance
        vm.prank(issuer);
        vc.deactivateFormat(fId);

        // Previously issued VC is still visible
        VCRegistry.Issued[] memory issued = vc.getIssuedToSubject(requester);
        assertEq(issued.length, 1);
    }

    // ── listFormats pagination ────────────────────────────────────────────────

    function test_listFormats_pagination() public {
        vm.startPrank(issuer);
        for (uint i; i < 5; i++) {
            vc.registerFormat(string(abi.encodePacked("VC", bytes1(uint8(0x41 + i)))));
        }
        vm.stopPrank();

        (VCRegistry.Format[] memory page1, uint256 next1) = vc.listFormats(0, 3);
        assertEq(page1.length, 3);
        assertEq(next1, 3);

        (VCRegistry.Format[] memory page2, uint256 next2) = vc.listFormats(next1, 3);
        assertEq(page2.length, 2);
        assertEq(next2, 0); // exhausted

        (VCRegistry.Format[] memory empty, ) = vc.listFormats(5, 10);
        assertEq(empty.length, 0);
    }

    // ── reissuance allowed ────────────────────────────────────────────────────

    function test_reissuance_allowed() public {
        (uint256 fId, uint256 rId1) = _registerAndRequest();
        vm.prank(issuer);
        vc.approveRequest(rId1, "first", keccak256("v1"));

        // Same requester can request again
        vm.prank(requester);
        uint256 rId2 = vc.requestVc(fId, "did:key:zABC123");
        vm.prank(issuer);
        vc.approveRequest(rId2, "second", keccak256("v2"));

        VCRegistry.Issued[] memory issued = vc.getIssuedToSubject(requester);
        assertEq(issued.length, 2);
    }

    // ── indexing by issuer ────────────────────────────────────────────────────

    function test_requests_indexed_by_issuer() public {
        _registerAndRequest();
        VCRegistry.Request[] memory incoming = vc.getRequestsByIssuer(issuer);
        assertEq(incoming.length, 1);
        assertEq(incoming[0].requester, requester);
    }

    // ── events ────────────────────────────────────────────────────────────────

    function test_approve_emits_event() public {
        (, uint256 rId) = _registerAndRequest();
        bytes32 hash = keccak256("vc");

        vm.prank(issuer);
        vm.expectEmit(true, true, false, true);
        emit VCRegistry.Approved(rId, 0, hash);
        vc.approveRequest(rId, "details", hash);
    }

    function test_reject_emits_event() public {
        (, uint256 rId) = _registerAndRequest();

        vm.prank(issuer);
        vm.expectEmit(true, false, false, false);
        emit VCRegistry.Rejected(rId);
        vc.rejectRequest(rId);
    }
}
