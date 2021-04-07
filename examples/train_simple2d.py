#!/usr/bin/env python3

# ELEKTRONN3 - Neural Network Toolkit
#
# Copyright (c) 2017 - now
# Max Planck Institute of Neurobiology, Munich, Germany
# Authors: Martin Drawitsch, Philipp Schubert

"""
Demo of a 2D semantic segmentation workflow.

It doesn't really learn anything useful, since the dataset
is far too small. It just serves as a quick demo for how 2D stuff can
be implemented.
"""

import argparse
import os
import random

import torch
from torch import nn
from torch import optim
import numpy as np

# Don't move this stuff, it needs to be run this early to work
import elektronn3
elektronn3.select_mpl_backend('Agg')

from elektronn3.training import Trainer, Backup
from elektronn3.training import metrics
from elektronn3.data import SimpleNeuroData2d, transforms
from elektronn3.models.unet import UNet


parser = argparse.ArgumentParser(description='Train a network.')
parser.add_argument('--disable-cuda', action='store_true', help='Disable CUDA')
parser.add_argument('-n', '--exp-name', default=None, help='Manually set experiment name')
parser.add_argument(
    '-m', '--max-steps', type=int, default=500000,
    help='Maximum number of training steps to perform.'
)
parser.add_argument(
    '-r', '--resume', metavar='PATH',
    help='Path to pretrained model state dict from which to resume training.'
)
parser.add_argument('--seed', type=int, default=0, help='Base seed for all RNGs.')
parser.add_argument(
    '--deterministic', action='store_true',
    help='Run in fully deterministic mode (at the cost of execution speed).'
)
args = parser.parse_args()

# Set up all RNG seeds, set level of determinism
random_seed = args.seed
torch.manual_seed(random_seed)
np.random.seed(random_seed)
random.seed(random_seed)
deterministic = args.deterministic
if deterministic:
    torch.backends.cudnn.deterministic = True
else:
    torch.backends.cudnn.benchmark = True  # Improves overall performance in *most* cases

if not args.disable_cuda and torch.cuda.is_available():
    device = torch.device('cuda')
else:
    device = torch.device('cpu')

print(f'Running on device: {device}')

out_channels = 2
model = UNet(
    out_channels=out_channels,
    n_blocks=4,
    start_filts=32,
    activation='relu',
    normalization='batch',
    dim=2
).to(device)

# USER PATHS
save_root = os.path.expanduser('~/e3training/')

max_steps = args.max_steps
lr = 0.0004
lr_stepsize = 1000
lr_dec = 0.995
batch_size = 1

if args.resume is not None:  # Load pretrained network params
    model.load_state_dict(torch.load(os.path.expanduser(args.resume)))

dataset_mean = (143.97594,)
dataset_std = (44.264744,)

# Transformations to be applied to samples before feeding them to the network
common_transforms = [
    transforms.Normalize(mean=dataset_mean, std=dataset_std, inplace=True)
]
train_transform = transforms.Compose(common_transforms + [
    transforms.RandomCrop((128, 128)),  # Use smaller patches for training
    transforms.RandomFlip(),
    transforms.AdditiveGaussianNoise(prob=0.5, sigma=0.1)
])
valid_transform = transforms.Compose(common_transforms + [
    transforms.RandomCrop((144, 144))
])
# Specify data set
train_dataset = SimpleNeuroData2d(train=True, transform=train_transform,
                                  out_channels=out_channels)
valid_dataset = SimpleNeuroData2d(train=False, transform=valid_transform,
                                  out_channels=out_channels)

# Set up optimization
optimizer = optim.Adam(
    model.parameters(),
    weight_decay=0.5e-4,
    lr=lr,
    amsgrad=True
)
lr_sched = optim.lr_scheduler.StepLR(optimizer, lr_stepsize, lr_dec)

# Validation metrics
valid_metrics = {}
for evaluator in [metrics.Accuracy, metrics.Precision, metrics.Recall, metrics.DSC, metrics.IoU]:
    valid_metrics[f'val_{evaluator.name}_mean'] = evaluator()  # Mean metrics
    for c in range(out_channels):
        valid_metrics[f'val_{evaluator.name}_c{c}'] = evaluator(c)

criterion = nn.CrossEntropyLoss().to(device)

# Create trainer
trainer = Trainer(
    model=model,
    criterion=criterion,
    optimizer=optimizer,
    device=device,
    train_dataset=train_dataset,
    valid_dataset=valid_dataset,
    batch_size=batch_size,
    num_workers=1,
    save_root=save_root,
    exp_name=args.exp_name,
    save_jit='script',
    schedulers={"lr": lr_sched},
    valid_metrics=valid_metrics,
    out_channels=out_channels,
)

# Archiving training script, src folder, env info
bk = Backup(script_path=__file__,
            save_path=trainer.save_path).archive_backup()

# Start training
trainer.run(max_steps)
