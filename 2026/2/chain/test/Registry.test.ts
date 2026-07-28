import { expect } from "chai";
import { ethers } from "hardhat";

describe("Registry", function () {
  async function deployRegistryFixture() {
    const [owner, otherAccount] = await ethers.getSigners();
    const Registry = await ethers.getContractFactory("Registry");
    const registry = await Registry.deploy();
    return { registry, owner, otherAccount };
  }

  it("Should register a new artifact", async function () {
    const { registry, owner } = await deployRegistryFixture();
    const promptHash = ethers.id("test prompt");
    const worldState = {
      modelId: ethers.ZeroHash,
      promptHash: promptHash,
      scriptHash: ethers.ZeroHash,
      geometryHashA: ethers.ZeroHash,
      geometryHashB: ethers.ZeroHash,
      producer: owner.address,
      modelProvider: owner.address,
      currentOwner: owner.address,
      bloomFilterRoot: ethers.ZeroHash,
      status: 0, // REGISTERED
      timestamp: Math.floor(Date.now() / 1000),
      ipfsCid: "QmTest"
    };

    await expect(registry.register(promptHash, worldState))
      .to.emit(registry, "Registered")
      .withArgs(promptHash, owner.address, anyValue => true);

    const savedState = await registry.verify(promptHash);
    expect(savedState.ipfsCid).to.equal("QmTest");
  });
});
