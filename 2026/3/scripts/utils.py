import numpy as np
from sklearn.metrics import roc_curve


def compute_eer(labels, scores):
    """
    labels : 1 = bonafide, 0 = spoof
    scores : 모델의 bonafide 클래스 확률 (softmax 출력의 index 1)
    """
    fpr, tpr, thresholds = roc_curve(labels, scores, pos_label=1)
    fnr = 1 - tpr  # FRR = 1 - TPR

    # FAR과 FRR이 가장 가까운 지점
    eer_idx = np.nanargmin(np.abs(fnr - fpr))
    eer = (fpr[eer_idx] + fnr[eer_idx]) / 2
    return eer
