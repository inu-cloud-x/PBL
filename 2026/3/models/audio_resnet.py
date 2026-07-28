from torchvision import models
import torch.nn as nn

def build_model(num_classes=2):
    model = models.resnet18(weights=None)
    
    model.conv1 = nn.Conv2d(
        in_channels=1,
        out_channels=model.conv1.out_channels,
        kernel_size=model.conv1.kernel_size,
        stride=model.conv1.stride,
        padding=model.conv1.padding,
        bias=(model.conv1.bias is not None),
    )
    
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model
