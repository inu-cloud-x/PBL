import torch
from torch import Tensor
from torch.utils.data import Dataset
import librosa
import numpy as np
import warnings

warnings.filterwarnings(
    "ignore",
    message="PySoundFile failed. Trying audioread instead.",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message="librosa.core.audio.__audioread_load",
    category=FutureWarning,
)

___author__ = "Hemlata Tak"
__email__ = "tak@eurecom.fr"


def genSpoof_list(dir_meta):

    d_meta = {}
    file_list = []
    with open(dir_meta, "r") as f:
        l_meta = f.readlines()

    for line in l_meta:
        _, key, _, _, label = line.strip().split()

        file_list.append(key)
        d_meta[key] = 1 if label == "bonafide" else 0
    return d_meta, file_list


def pad(x, max_len=64600):
    x_len = x.shape[0]
    if x_len >= max_len:
        return x[:max_len]
    # need to pad
    num_repeats = int(max_len / x_len) + 1
    padded_x = np.tile(x, (1, num_repeats))[:, :max_len][0]
    return padded_x


class SpoofLoader(Dataset):
    def __init__(self, list_IDs, labels, base_dir):
        """self.list_IDs	: list of strings (each string: utt key),
        self.labels      : dictionary (key: utt key, value: label integer)"""

        self.list_IDs = list_IDs
        self.labels = labels
        self.base_dir = base_dir
        self.cut = 64600  # take ~4 sec audio (64600 samples)

    def __len__(self):
        return len(self.list_IDs)

    def __getitem__(self, index):

        utt_id = self.list_IDs[index]
        if isinstance(self.base_dir, str):
            X, fs = librosa.load(self.base_dir + utt_id + ".flac", sr=16000)
        else:
            try:
                X, fs = librosa.load(self.base_dir[0] + utt_id + ".flac", sr=16000)
            except:
                X, fs = librosa.load(self.base_dir[1] + utt_id + ".flac", sr=16000)
        
        X_pad = pad(X, self.cut)
        
        mel = librosa.feature.melspectrogram(
            y=X_pad,
            sr=16000,
            n_mels=64,
            n_fft=400,
            hop_length=160,
            power=2.0,
        )

        mel_db = librosa.power_to_db(mel, ref=np.max)
        
        x_inp = torch.from_numpy(mel_db).float().unsqueeze(0)

        target = self.labels[utt_id]

        return x_inp, target
