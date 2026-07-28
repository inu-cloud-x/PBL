from pathlib import Path
import torch
from models.audio_resnet import build_model

WEIGHTS_DIR = Path('weights')
WEIGHTS_DIR.mkdir(exist_ok=True)
OUTPUT_PATH = WEIGHTS_DIR / 'global_round_0.pt'


def main():
    model = build_model(num_classes=2)
    torch.save(model.state_dict(), OUTPUT_PATH)
    print(f'Saved: {OUTPUT_PATH.resolve()}')
    print(f'fc.out_features = {model.fc.out_features}')


if __name__ == '__main__':
    main()
