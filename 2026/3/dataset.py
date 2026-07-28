import os
import random
from collections import defaultdict

if __name__ == "__main__":
    file_path  = "data/df/en/ASVspoof2019.LA.cm.dev.trl.txt"
    train_path = "data/df/en/19LA_train_info.txt"
    eval_path  = "data/df/en/19LA_eval_info.txt"

    TRAIN_PER_ALGO = 300
    EVAL_PER_ALGO  = 300

    # 1. 파일 읽기 및 algorithm별 그룹핑
    algo_dict = defaultdict(list)

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            # 형식: speaker filename - algorithm label
            algorithm = parts[3]
            algo_dict[algorithm].append(line)

    train_lines = []
    eval_lines  = []

    # 2. algorithm별로 shuffle 후 train/eval 분리 (겹치지 않게)
    for algo, lines in algo_dict.items():
        random.shuffle(lines)

        needed = TRAIN_PER_ALGO + EVAL_PER_ALGO
        if len(lines) < needed:
            print(f"[경고] {algo}: 데이터 {len(lines)}개로 {needed}개 요청 불가")
            continue

        train_lines.extend(lines[:TRAIN_PER_ALGO])
        eval_lines.extend(lines[TRAIN_PER_ALGO:needed])
        print(f"  {algo}: train {TRAIN_PER_ALGO}개 / eval {EVAL_PER_ALGO}개 추출")

    # 3. 각각 파일 저장
    for path, data in [(train_path, train_lines), (eval_path, eval_lines)]:
        with open(path, "w", encoding="utf-8") as f:
            for line in data:
                f.write(line + "\n")

    print(f"\ntrain: {len(train_lines)}개 → {train_path}")
    print(f"eval:  {len(eval_lines)}개  → {eval_path}")
