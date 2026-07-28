// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IMiniENS {
    function reverseLookup(address owner) external view returns (string memory);
}

contract VCRegistry {
    IMiniENS public immutable ens;

    constructor(address ensAddr) {
        ens = IMiniENS(ensAddr);
    }

    // ── Types ─────────────────────────────────────────────────────────────────

    struct Format {
        uint256 id;
        address issuer;
        string  name;
        bool    active;
        uint64  createdAt;
    }

    enum Status { Pending, Approved, Rejected }

    struct Request {
        uint256 id;
        uint256 formatId;
        address requester;
        string  subjectDid;
        Status  status;
        uint64  createdAt;
    }

    struct Issued {
        uint256 id;
        uint256 formatId;
        address issuer;
        address subject;
        string  details;
        bytes32 jsonHash;
        uint64  issuedAt;
        uint64  expiresAt;
    }

    // ── Storage ───────────────────────────────────────────────────────────────

    uint256 public formatCount;
    uint256 public requestCount;
    uint256 public issuedCount;

    mapping(uint256 => Format)  private _formats;
    mapping(uint256 => Request) private _requests;
    mapping(uint256 => Issued)  private _issued;

    // index: issuer address → list of request ids
    mapping(address => uint256[]) private _requestsByIssuer;
    // index: requester address → list of request ids
    mapping(address => uint256[]) private _requestsByRequester;
    // index: subject address → list of issued ids
    mapping(address => uint256[]) private _issuedToSubject;

    // ── Events ────────────────────────────────────────────────────────────────

    event FormatRegistered(uint256 indexed id, address indexed issuer, string name);
    event FormatDeactivated(uint256 indexed id);
    event Requested(uint256 indexed id, uint256 indexed formatId, address indexed requester);
    event Approved(uint256 indexed requestId, uint256 indexed issuedId, bytes32 jsonHash);
    event Rejected(uint256 indexed requestId);

    // ── Write functions ───────────────────────────────────────────────────────

    function registerFormat(string calldata name) external returns (uint256) {
        require(
            bytes(name).length >= 1 && bytes(name).length <= 40,
            "name 1-40 bytes"
        );
        require(
            bytes(ens.reverseLookup(msg.sender)).length > 0,
            "ENS name required"
        );

        uint256 id = formatCount++;
        _formats[id] = Format({
            id:        id,
            issuer:    msg.sender,
            name:      name,
            active:    true,
            createdAt: uint64(block.timestamp)
        });

        emit FormatRegistered(id, msg.sender, name);
        return id;
    }

    function deactivateFormat(uint256 formatId) external {
        Format storage f = _formats[formatId];
        require(formatId < formatCount, "format not found");
        require(f.issuer == msg.sender, "not issuer");
        require(f.active, "already inactive");

        f.active = false;
        emit FormatDeactivated(formatId);
    }

    function requestVc(uint256 formatId, string calldata subjectDid) external returns (uint256) {
        require(formatId < formatCount, "format not found");
        require(_formats[formatId].active, "format inactive");
        require(bytes(subjectDid).length <= 200, "subjectDid too long");

        uint256 id = requestCount++;
        _requests[id] = Request({
            id:         id,
            formatId:   formatId,
            requester:  msg.sender,
            subjectDid: subjectDid,
            status:     Status.Pending,
            createdAt:  uint64(block.timestamp)
        });

        address issuer = _formats[formatId].issuer;
        _requestsByIssuer[issuer].push(id);
        _requestsByRequester[msg.sender].push(id);

        emit Requested(id, formatId, msg.sender);
        return id;
    }

    function approveRequest(
        uint256 requestId,
        string calldata details,
        bytes32 jsonHash
    ) external returns (uint256 issuedId) {
        require(requestId < requestCount, "request not found");
        Request storage req = _requests[requestId];
        require(req.status == Status.Pending, "not pending");

        Format storage fmt = _formats[req.formatId];
        require(fmt.issuer == msg.sender, "not issuer");
        require(
            bytes(details).length >= 1 && bytes(details).length <= 100,
            "details 1-100 bytes"
        );
        require(jsonHash != bytes32(0), "hash required");

        req.status = Status.Approved;

        issuedId = issuedCount++;
        uint64 issuedAt  = uint64(block.timestamp);
        uint64 expiresAt = issuedAt + uint64(365 days);

        _issued[issuedId] = Issued({
            id:        issuedId,
            formatId:  req.formatId,
            issuer:    msg.sender,
            subject:   req.requester,
            details:   details,
            jsonHash:  jsonHash,
            issuedAt:  issuedAt,
            expiresAt: expiresAt
        });

        _issuedToSubject[req.requester].push(issuedId);

        emit Approved(requestId, issuedId, jsonHash);
    }

    function rejectRequest(uint256 requestId) external {
        require(requestId < requestCount, "request not found");
        Request storage req = _requests[requestId];
        require(req.status == Status.Pending, "not pending");

        Format storage fmt = _formats[req.formatId];
        require(fmt.issuer == msg.sender, "not issuer");

        req.status = Status.Rejected;
        emit Rejected(requestId);
    }

    // ── View functions ────────────────────────────────────────────────────────

    function getFormat(uint256 formatId) external view returns (Format memory) {
        require(formatId < formatCount, "format not found");
        return _formats[formatId];
    }

    /**
     * Paginated list of all formats.
     * cursor=0 to start; returns nextCursor=0 when exhausted.
     */
    function listFormats(
        uint256 cursor,
        uint256 limit
    ) external view returns (Format[] memory formats, uint256 nextCursor) {
        uint256 total = formatCount;
        if (cursor >= total || limit == 0) {
            return (new Format[](0), 0);
        }

        uint256 end = cursor + limit;
        if (end > total) end = total;

        formats = new Format[](end - cursor);
        for (uint256 i = cursor; i < end; i++) {
            formats[i - cursor] = _formats[i];
        }
        nextCursor = end < total ? end : 0;
    }

    function getRequestsByIssuer(address issuer) external view returns (Request[] memory) {
        uint256[] storage ids = _requestsByIssuer[issuer];
        Request[] memory result = new Request[](ids.length);
        for (uint256 i; i < ids.length; i++) {
            result[i] = _requests[ids[i]];
        }
        return result;
    }

    function getRequestsByRequester(address requester) external view returns (Request[] memory) {
        uint256[] storage ids = _requestsByRequester[requester];
        Request[] memory result = new Request[](ids.length);
        for (uint256 i; i < ids.length; i++) {
            result[i] = _requests[ids[i]];
        }
        return result;
    }

    function getIssuedToSubject(address subject) external view returns (Issued[] memory) {
        uint256[] storage ids = _issuedToSubject[subject];
        Issued[] memory result = new Issued[](ids.length);
        for (uint256 i; i < ids.length; i++) {
            result[i] = _issued[ids[i]];
        }
        return result;
    }
}
