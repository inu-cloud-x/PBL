import json
import hashlib
import argparse
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms, models
from web3 import Web3
import numpy as np
from tqdm import tqdm

from scripts.dataloader import genSpoof_list, SpoofLoader
from scripts.utils import compute_eer
from models.audio_resnet import build_model

# --- 설정 ------------------------------------------------
CONTRACT_INFO_PATH = Path("scripts/contract_info.json")
WEIGHTS_DIR = Path("weights")
WEIGHTS_DIR.mkdir(exist_ok=True)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
NUM_CLIENTS = 2
LOCAL_EPOCHS = 5
BATCH_SIZE = 32
LR = 1e-4


# --- Speech deepfake 데이터 분할 ----------------------
def get_spoof_loader(client_idx: int, num_client: int = NUM_CLIENTS):
    '''
    client_idx == 0: ko
    client_idx == 1: en
    '''
    lang = "ko" if client_idx == 0 else "en"
    
    trn_meta_path = f"data/df/{lang}/train_info.txt"
    eval_meta_path = f"data/df/{lang}/eval_info.txt"
    
    trn_flac_path = f"data/df/{lang}/flac/"
    eval_flac_path = f"data/df/{lang}/flac/"
    
    trn_label, trn_file = genSpoof_list(trn_meta_path)
    print("no. of training trials", len(trn_file))
    trn_set = SpoofLoader(
        list_IDs = trn_file,
        labels = trn_label,
        base_dir = trn_flac_path
    )
    trn_loader = DataLoader(trn_set, batch_size=BATCH_SIZE, shuffle=True,
                            num_workers=2, pin_memory=True)
    
    eval_label, eval_file = genSpoof_list(eval_meta_path)
    print("no. of evaluation trials", len(eval_file))
    eval_set = SpoofLoader(
        list_IDs = eval_file,
        labels = eval_label,
        base_dir = eval_flac_path
    )
    eval_loader = DataLoader(eval_set, batch_size=BATCH_SIZE, shuffle=False,
                             num_workers=2)
    
    return trn_loader, eval_loader, len(trn_loader), len(eval_loader)


# --- 로컬 학습 -------------------------------------------
def local_train(model, client_idx: int):
    model = model.to(DEVICE)
    model.train()
    trn_loader, eval_loader, trn_num_samples, eval_num_samples = get_spoof_loader(client_idx)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)

    # --- training -------------------------------------------
    for epoch in range(LOCAL_EPOCHS):
        total_loss = 0.0
        for feats, labels in tqdm(trn_loader, ncols=100, desc="Training"):
            feats = feats.to(DEVICE, non_blocking=True)
            labels = labels.to(DEVICE, non_blocking=True)
            optimizer.zero_grad()
            loss = criterion(model(feats), labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        avg_loss = total_loss / len(trn_loader)
        print(f"[train] epoch {epoch+1}/{LOCAL_EPOCHS} | loss: {avg_loss:.4f}")
    
    # --- evaluation -------------------------------------------
    model.eval()
    all_scores = []
    all_labels = []
    with torch.no_grad():
        for feats, labels in tqdm(eval_loader, ncols=100, desc="Evaluation"):
            feats = feats.to(DEVICE, non_blocking=True)
            labels = labels.to(DEVICE, non_blocking=True)
            
            logits = model(feats)
            probs  = torch.softmax(logits, dim=1)
            
            all_scores.append(probs[:, 1].cpu().numpy())
            all_labels.append(labels.cpu().numpy())
    
    all_scores = np.concatenate(all_scores)
    all_labels = np.concatenate(all_labels)
    
    eer = compute_eer(all_labels, all_scores)
    lang = "ko" if client_idx == 0 else "en"
    print(f"[eval]  client {client_idx} ({lang}) | EER: {eer*100:.2f}%")
      

    state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    torch.cuda.empty_cache()
    return state, trn_num_samples, eer * 100


# --- weight 파일 SHA256 해시 계산 ------------------------
def compute_file_hash(file_path: Path) -> bytes:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        sha256.update(f.read())
    return sha256.digest()


# --- 메인 클라이언트 함수 --------------------------------
def run_client(client_idx: int, round_num: int, global_weight_path: Path):
    print(f"[client {client_idx}] round {round_num} start | device: {DEVICE}")

    # 1) contract_info.json 로드
    info = json.loads(CONTRACT_INFO_PATH.read_text())
    w3 = Web3(Web3.HTTPProvider(info["ganache_url"]))
    assert w3.is_connected(), "Ganache 연결 실패. ganache 실행 여부를 확인하세요."
    contract = w3.eth.contract(
        address=info["address"],
        abi=info["abi"]
    )
    client_account = info["client_accounts"][client_idx]
    print(f"[client {client_idx}] account: {client_account}")

    # 2) 글로벌 모델 로드
    model = build_model(num_classes=2)
    model.load_state_dict(torch.load(global_weight_path, map_location=DEVICE, weights_only=False))
    print(f"[client {client_idx}] global weight loaded: {global_weight_path}")

    # 3) 로컬 학습
    state, num_samples, eer = local_train(model, client_idx)
    print(f"[client {client_idx}] local train done | samples: {num_samples} | EER: {eer:.2f}%")

    # 4) weight 파일 저장
    weight_path = WEIGHTS_DIR / f"client_{client_idx}_round_{round_num}.pt"
    torch.save(state, weight_path)
    print(f"[client {client_idx}] weight saved: {weight_path}")

    # 5) SHA256 해시 계산
    file_hash = compute_file_hash(weight_path)

    # 6) 블록체인에 해시 제출
    tx_hash = contract.functions.submitWeight(
        round_num,
        file_hash
    ).transact({
        "from": client_account,
        "gas": 200_000
    })
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"[client {client_idx}] tx submitted")
    print(f"  tx hash   : {tx_hash.hex()}")
    print(f"  block num : {receipt.blockNumber}")

    # 7) 현재 제출 현황 조회
    submitted_count = contract.functions.getSubmittedCount(round_num).call()
    print(f"[client {client_idx}] submitted count: {submitted_count} / {info['num_clients']}")

    return state, num_samples


# --- main ----------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FL Client")
    parser.add_argument("--client_idx", type=int, required=True,
                        help="클라이언트 인덱스 (0, 1)")
    parser.add_argument("--round_num", type=int, required=True,
                        help="현재 라운드 번호")
    parser.add_argument("--global_weight", type=str, required=True,
                        help="글로벌 모델 weight 파일 경로")
    args = parser.parse_args()

    run_client(
        client_idx=args.client_idx,
        round_num=args.round_num,
        global_weight_path=Path(args.global_weight)
    )