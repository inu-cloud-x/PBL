// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract MiniENS {
    mapping(bytes32 => address) private _nameToAddr;
    mapping(address => string)  private _addrToName;

    event Registered(bytes32 indexed nameHash, string name, address indexed owner);
    event Released(bytes32 indexed nameHash, address indexed owner);

    /// @notice 3~32자, 소문자 알파벳·숫자·하이픈만 허용. 첫/끝 글자는 하이픈 금지.
    function register(string calldata name) external {
        bytes32 h = _validate(name);
        require(_nameToAddr[h] == address(0), "name taken");
        require(bytes(_addrToName[msg.sender]).length == 0, "already has name");
        _nameToAddr[h] = msg.sender;
        _addrToName[msg.sender] = name;
        emit Registered(h, name, msg.sender);
    }

    function release() external {
        string memory name = _addrToName[msg.sender];
        require(bytes(name).length > 0, "no name registered");
        bytes32 h = keccak256(bytes(name));
        delete _nameToAddr[h];
        delete _addrToName[msg.sender];
        emit Released(h, msg.sender);
    }

    function resolve(string calldata name) external view returns (address) {
        return _nameToAddr[keccak256(bytes(name))];
    }

    function reverseLookup(address addr) external view returns (string memory) {
        return _addrToName[addr];
    }

    function _validate(string calldata name) internal pure returns (bytes32) {
        bytes memory b = bytes(name);
        require(b.length >= 3 && b.length <= 32, "length 3-32");
        require(b[0] != 0x2d && b[b.length - 1] != 0x2d, "no leading/trailing hyphen");
        for (uint256 i; i < b.length; i++) {
            bytes1 c = b[i];
            bool ok = (c >= 0x61 && c <= 0x7a)  // a-z
                   || (c >= 0x30 && c <= 0x39)  // 0-9
                   || c == 0x2d;                // -
            require(ok, "invalid char");
        }
        return keccak256(b);
    }
}
