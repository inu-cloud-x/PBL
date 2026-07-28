import json
from pathlib import Path
from web3 import Web3
from solcx import compile_source, install_solc

# ─── 설정 ────────────────────────────────────────────
GANACHE_URL = "http://127.0.0.1:8545"
NUM_CLIENTS = 2
CONTRACT_PATH = Path("contracts/FLAggregator.sol")
OUTPUT_PATH = Path("scripts/contract_info.json")

def deploy():
    # 1) Ganache 연결
    w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
    assert w3.is_connected(), "Ganache에 연결 불가능"
    print(f"Ganache 연결 성공 | 블록번호: {w3.eth.block_number}")

    # 2) 계좌 확인
    accounts = w3.eth.accounts
    server_account = accounts[0]
    print(f"서버 계좌: {server_account}")
    print(f"사용 가능한 계좌 수: {len(accounts)}개")

    # 3) Solidity 컴파일
    install_solc("0.8.0")
    source_code = CONTRACT_PATH.read_text()
    compiled = compile_source(
        source_code,
        output_values=["abi", "bin"],
        solc_version="0.8.0"
    )
    contract_id = list(compiled.keys())[0]
    abi = compiled[contract_id]["abi"]
    bytecode = compiled[contract_id]["bin"]
    print("Solidity 컴파일 성공")

    # 4) 컨트랙트 배포
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = Contract.constructor(NUM_CLIENTS).transact({
        "from": server_account,
        "gas": 3_000_000
    })
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = tx_receipt.contractAddress
    print(f"컨트랙트 배포 완료")
    print(f"   주소: {contract_address}")
    print(f"   트랜잭션 해시: {tx_hash.hex()}")

    # 5) 배포 정보 저장 (server.py, client.py에서 불러옴)
    contract_info = {
        "address": contract_address,
        "abi": abi,
        "server_account": server_account,
        "client_accounts": accounts[1:NUM_CLIENTS+1],
        "ganache_url": GANACHE_URL,
        "num_clients": NUM_CLIENTS
    }
    OUTPUT_PATH.write_text(json.dumps(contract_info, indent=2))
    print(f"배포 정보 저장 완료: {OUTPUT_PATH}")

    return contract_info


if __name__ == "__main__":
    deploy()