import json
import hashlib
import warnings
from pathlib import Path
from collections import OrderedDict

import torch
import torch.nn as nn
from torchvision import models, datasets, transforms
from torch.utils.data import DataLoader
from web3 import Web3
from tqdm import tqdm
import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)
from scripts.dataloader import genSpoof_list, SpoofLoader
from scripts.utils import compute_eer
from models.audio_resnet import build_model

# --- 설정 ------------------------------------------------
CONTRACT_INFO_PATH = Path("scripts/contract_info.json")
WEIGHTS_DIR = Path("weights")
NUM_ROUNDS = 5
NUM_CLIENTS = 2
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# --- FedAvg 집계 -----------------------------------------
def fedavg(state_dicts, sample_counts):
    total = sum(sample_counts)
    new_state = OrderedDict()
    for key in state_dicts[0].keys():
        new_state[key] = sum(
            state_dicts[i][key] * (sample_counts[i] / total)
            for i in range(len(state_dicts))
        )
    return new_state


# --- weight 파일 해시 계산 --------------------------------
def compute_file_hash(file_path: Path) -> bytes:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        sha256.update(f.read())
    return sha256.digest()


# --- 글로벌 모델 검증 (val accuracy) ---------------------
@torch.no_grad()
def evaluate(model):
    ko_flac_path = "data/df/ko/flac/"
    en_flac_path = "data/df/en/flac/"
    
    ko_eval_meta_path = "data/df/ko/eval_info.txt"
    ko_label, ko_file = genSpoof_list(ko_eval_meta_path)
    
    en_eval_meta_path = "data/df/en/eval_info.txt"
    en_label, en_file = genSpoof_list(en_eval_meta_path)
    
    total_label = {**ko_label, **en_label}
    total_file = ko_file + en_file
    
    print("no. of total evaluation trials", len(total_file))
    total_set = SpoofLoader(
        list_IDs = total_file,
        labels = total_label,
        base_dir = [ko_flac_path, en_flac_path]
    )
    
    loader = DataLoader(total_set, batch_size=64, shuffle=False, num_workers=2)
    model = model.to(DEVICE)
    
    model.eval()
    all_scores = []
    all_labels = []
    with torch.no_grad():
        for feats, labels in tqdm(loader, ncols=100, desc="Evaluation"):
            feats = feats.to(DEVICE, non_blocking=True)
            labels = labels.to(DEVICE, non_blocking=True)
            
            logits = model(feats)
            probs  = torch.softmax(logits, dim=1)
            
            all_scores.append(probs[:, 1].cpu().numpy())
            all_labels.append(labels.cpu().numpy())
    
    all_scores = np.concatenate(all_scores)
    all_labels = np.concatenate(all_labels)
    
    # 전체 EER
    eer_total = compute_eer(all_labels, all_scores) * 100.0

    # ko / en 구간 인덱스 계산
    n_ko = len(ko_file)

    scores_ko  = all_scores[:n_ko]
    labels_ko  = all_labels[:n_ko]
    scores_en  = all_scores[n_ko:]
    labels_en  = all_labels[n_ko:]

    eer_ko = compute_eer(labels_ko, scores_ko) * 100.0
    eer_en = compute_eer(labels_en, scores_en) * 100.0

    print(f"EER total: {eer_total:.2f}%")
    print(f"EER ko   : {eer_ko:.2f}%")
    print(f"EER en   : {eer_en:.2f}%")

    return eer_total


# --- weight 무결성 검증 ----------------------------------
def verify_weights(contract, round_num, client_accounts):
    print(f"[server] weight 무결성 검증 시작")
    verified = []
    for i, account in enumerate(client_accounts):
        weight_path = WEIGHTS_DIR / f"client_{i}_round_{round_num}.pt"
        if not weight_path.exists():
            print(f"  [warn] client {i} weight 파일 없음: {weight_path}")
            verified.append(False)
            continue

        file_hash = compute_file_hash(weight_path)
        on_chain = contract.functions.verifyWeight(
            round_num,
            account,
            file_hash
        ).call()

        status = "OK" if on_chain else "MISMATCH"
        print(f"  client {i} | hash verify: {status}")
        verified.append(on_chain)

    return all(verified)


# --- 메인 서버 루프 ---------------------------------------
def run_server():
    print(f"[server] start | device: {DEVICE}")

    # 1) contract_info.json 로드
    info = json.loads(CONTRACT_INFO_PATH.read_text())
    w3 = Web3(Web3.HTTPProvider(info["ganache_url"]))
    assert w3.is_connected(), "Ganache 연결 실패. ganache 실행 여부를 확인"
    contract = w3.eth.contract(
        address=info["address"],
        abi=info["abi"]
    )
    server_account = info["server_account"]
    client_accounts = info["client_accounts"]
    print(f"[server] contract address: {info['address']}")
    print(f"[server] server account  : {server_account}")

    # 2) FL 라운드 반복
    for round_num in range(1, NUM_ROUNDS + 1):
        print(f"\n{'=' * 55}")
        print(f"[server] round {round_num} / {NUM_ROUNDS}")
        print(f"{'=' * 55}")

        global_weight_path = WEIGHTS_DIR / f"global_round_{round_num - 1}.pt"

        # 3) startRound() 트랜잭션
        tx = contract.functions.startRound().transact({
            "from": server_account,
            "gas": 100_000
        })
        w3.eth.wait_for_transaction_receipt(tx)
        current_round = contract.functions.currentRound().call()
        print(f"[server] startRound() | currentRound: {current_round}")

        # 4) 클라이언트 순차 실행
        sample_counts = []
        for client_idx in range(NUM_CLIENTS):
            print(f"\n[server] client {client_idx} 학습 시작")
            from scripts.client import run_client
            state_dict, num_samples = run_client(
                client_idx=client_idx,
                round_num=round_num,
                global_weight_path=global_weight_path
            )
            sample_counts.append(num_samples)

        # 5) AggregationReady 이벤트 확인
        submitted = contract.functions.getSubmittedCount(round_num).call()
        print(f"\n[server] submitted: {submitted} / {NUM_CLIENTS}")
        assert submitted >= NUM_CLIENTS, "제출 수 부족. 클라이언트 실행을 확인"

        # 6) weight 무결성 검증 (블록체인 해시 대조)
        all_verified = verify_weights(contract, round_num, client_accounts)
        assert all_verified, "weight 무결성 검증 실패."
        print(f"[server] weight 무결성 검증 통과")

        # 7) FedAvg 집계
        state_dicts = []
        for client_idx in range(NUM_CLIENTS):
            weight_path = WEIGHTS_DIR / f"client_{client_idx}_round_{round_num}.pt"
            state_dicts.append(
                torch.load(weight_path, map_location=DEVICE, weights_only=True)
            )
        new_global_state = fedavg(state_dicts, sample_counts)

        # 8) 새 글로벌 모델 저장
        global_model = build_model(num_classes=2)
        global_model.load_state_dict(new_global_state)
        new_global_path = WEIGHTS_DIR / f"global_round_{round_num}.pt"
        torch.save(global_model.state_dict(), new_global_path)
        print(f"[server] global model saved: {new_global_path}")

        # 9) markAggregated() 트랜잭션
        tx = contract.functions.markAggregated(round_num).transact({
            "from": server_account,
            "gas": 100_000
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx)
        print(f"[server] markAggregated() | block: {receipt.blockNumber}")

        # 10) 검증 정확도 측정
        eer = evaluate(global_model)
        print(f"[server] round {round_num} EER: {eer*100:.2f}")

    print(f"\n[server] training complete")
    print(f"[server] final model: {new_global_path}")


if __name__ == "__main__":
    run_server()