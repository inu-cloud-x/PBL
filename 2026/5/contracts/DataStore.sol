// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract DataStore {
    struct Entry {
        bytes data;
        uint256 timestamp;
    }

    mapping(address => Entry[]) private _entries;

    event Stored(address indexed user, uint256 index);
    event Removed(address indexed user, uint256 index);

    function store(bytes calldata value) external {
        require(value.length > 0 && value.length <= 300, "1-300 bytes");
        _entries[msg.sender].push(Entry(value, block.timestamp));
        emit Stored(msg.sender, _entries[msg.sender].length - 1);
    }

    /// @dev Swap-and-pop: 순서가 바뀔 수 있으므로 클라이언트에서 timestamp로 정렬
    function remove(uint256 index) external {
        Entry[] storage arr = _entries[msg.sender];
        require(index < arr.length, "out of bounds");
        arr[index] = arr[arr.length - 1];
        arr.pop();
        emit Removed(msg.sender, index);
    }

    function getAll(address user) external view returns (Entry[] memory) {
        return _entries[user];
    }
}
