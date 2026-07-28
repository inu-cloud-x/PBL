// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract VotingRegistry {
    enum Choice { Yes, No, Abstain }

    struct Proposal {
        address creator;
        string  title;          // max 100 bytes
        bytes   description;    // max 500 bytes
        uint64  deadline;       // Unix seconds (block.timestamp + duration)
        uint128 yesVotes;
        uint128 noVotes;
        uint128 abstainVotes;
    }

    uint256 public proposalCount;
    mapping(uint256 => Proposal)                 public proposals;
    mapping(uint256 => mapping(address => bool)) public hasVoted;

    uint256 public constant MIN_DURATION =  1 hours;
    uint256 public constant MAX_DURATION = 30 days;

    event ProposalCreated(uint256 indexed id, address indexed creator, string title, uint64 deadline);
    event VoteCast(uint256 indexed proposalId, address indexed voter, Choice choice);

    function createProposal(
        string  calldata title,
        bytes   calldata description,
        uint256 duration
    ) external {
        require(bytes(title).length > 0 && bytes(title).length <= 100, "title 1-100 bytes");
        require(description.length <= 500, "desc max 500 bytes");
        require(duration >= MIN_DURATION && duration <= MAX_DURATION, "invalid duration");

        uint256 id = proposalCount++;
        uint64  deadline = uint64(block.timestamp + duration);

        proposals[id] = Proposal({
            creator:      msg.sender,
            title:        title,
            description:  description,
            deadline:     deadline,
            yesVotes:     0,
            noVotes:      0,
            abstainVotes: 0
        });

        emit ProposalCreated(id, msg.sender, title, deadline);
    }

    function vote(uint256 proposalId, Choice choice) external {
        Proposal storage p = proposals[proposalId];
        require(p.deadline > 0,                         "proposal not found");
        require(block.timestamp < p.deadline,           "voting closed");
        require(!hasVoted[proposalId][msg.sender],      "already voted");

        hasVoted[proposalId][msg.sender] = true;

        if      (choice == Choice.Yes)     p.yesVotes++;
        else if (choice == Choice.No)      p.noVotes++;
        else                               p.abstainVotes++;

        emit VoteCast(proposalId, msg.sender, choice);
    }

    function getProposal(uint256 id) external view returns (Proposal memory) {
        return proposals[id];
    }
}
