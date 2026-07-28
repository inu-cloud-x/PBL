// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract FLAggregator {

    address public owner;           // 서버 계좌 주소
    uint public currentRound;       // 현재 라운드 번호
    uint public requiredClients;    // 집계에 필요한 최소 클라이언트 수

    // 라운드별 클라이언트 제출 기록
    // round => client_address => weight 파일 해시
    mapping(uint => mapping(address => bytes32)) public submissions;

    // 라운드별 제출 완료된 클라이언트 주소 목록
    mapping(uint => address[]) public submittedClients;

    // 라운드별 집계 완료 여부
    mapping(uint => bool) public roundAggregated;

    // ─── 이벤트 (Python에서 감지) ───────────────────
    event RoundStarted(uint round);
    event WeightSubmitted(uint round, address client, bytes32 weightHash);
    event AggregationReady(uint round, uint clientCount);
    event RoundAggregated(uint round);

    // ─── 생성자 ──────────────────────────────────────
    constructor(uint _requiredClients) {
        owner = msg.sender;
        requiredClients = _requiredClients;
        currentRound = 0;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only server can call this");
        _;
    }

    // ─── 서버가 새 라운드 시작 ────────────────────────
    function startRound() public onlyOwner {
        currentRound += 1;
        emit RoundStarted(currentRound);
    }

    // ─── 클라이언트가 weight 해시 제출 ───────────────
    function submitWeight(uint round, bytes32 weightHash) public {
        require(round == currentRound, "Wrong round number");
        require(
            submissions[round][msg.sender] == bytes32(0),
            "Already submitted this round"
        );

        submissions[round][msg.sender] = weightHash;
        submittedClients[round].push(msg.sender);

        emit WeightSubmitted(round, msg.sender, weightHash);

        // 충분한 클라이언트가 제출하면 집계 준비 완료 이벤트
        if (submittedClients[round].length >= requiredClients) {
            emit AggregationReady(round, submittedClients[round].length);
        }
    }

    // ─── 서버가 집계 완료 기록 ────────────────────────
    function markAggregated(uint round) public onlyOwner {
        require(!roundAggregated[round], "Already aggregated");
        roundAggregated[round] = true;
        emit RoundAggregated(round);
    }

    // ─── 조회 함수들 ──────────────────────────────────
    function getSubmittedCount(uint round) public view returns (uint) {
        return submittedClients[round].length;
    }

    function getSubmittedClients(uint round) public view returns (address[] memory) {
        return submittedClients[round];
    }

    function verifyWeight(uint round, address client, bytes32 hash) public view returns (bool) {
        return submissions[round][client] == hash;
    }
}