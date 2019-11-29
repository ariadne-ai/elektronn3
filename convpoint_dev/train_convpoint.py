# ELEKTRONN3 - Neural Network Toolkit
#
# Copyright (c) 2019 - now
# Max Planck Institute of Neurobiology, Munich, Germany
# Authors: Jonathan Klimesch

import os
import torch
import torch.nn.functional as func
import numpy as np
import convpoint_dev.metrics as metrics
import morphx.processing.clouds as clouds

from sklearn.metrics import confusion_matrix
from elektronn3.models.convpoint import ConvPoint
from morphx.data.torchset import TorchSet
from tqdm import tqdm

# SET UP ENVIRONMENT #

use_cuda = False

if use_cuda:
    device = torch.device('cuda')
else:
    device = torch.device('cpu')

# CREATE NETWORK #

input_channels = 1
# dendrite, axon, soma, bouton, terminal
output_channels = 5
model = ConvPoint(input_channels, output_channels).to(device)

if use_cuda:
    model.cuda()

# define parameters
epochs = 200
epoch_size = 4096
milestones = [60, 120]
lr = 1e-3
batch_size = 16
npoints = 1000
radius = 20000
n_classes = 5

# set paths
train_path = os.path.expanduser('~/gt/training/')
save_root = os.path.expanduser('~/gt/simple_training/')
folder = os.path.join(save_root, "SegSmall_b{}_r{}_s{}".format(batch_size, radius, npoints))
os.makedirs(folder, exist_ok=True)
logs = open(os.path.join(folder, "log.txt"), "w")

# PREPARE DATA SET #

# Transformations to be applied to samples before feeding them to the network
train_transform = clouds.Compose([clouds.RandomRotate(),
                                  clouds.RandomVariation(limits=(-1, 1)),
                                  clouds.Center()])

ds = TorchSet(train_path, radius, npoints, train_transform, epoch_size=epoch_size)
train_loader = torch.utils.data.DataLoader(ds, batch_size=batch_size, shuffle=True, num_workers=1)

# PREPARE AND START TRAINING #

# set up optimization
optimizer = torch.optim.Adam(model.parameters(), lr=lr)
scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer, milestones)

model.train()
for epoch in range(epochs):
    scheduler.step()
    cm = np.zeros((n_classes, n_classes))
    t = tqdm(train_loader, ncols=120, desc="Epoch {}".format(epoch))
    for pts, features, lbs in t:
        features.to(device)
        pts.to(device)
        lbs.to(device)

        optimizer.zero_grad()
        outputs = model(features, pts)

        loss = 0
        for i in range(pts.size(0)):
            loss = loss + func.cross_entropy(outputs[i], lbs[i])

        loss.backward()
        optimizer.step()

        outputs_np = outputs.cpu().detach().numpy()
        output_np = np.argmax(outputs_np, axis=2).copy()
        target_np = lbs.cpu().numpy().copy()

        cm_ = confusion_matrix(target_np.ravel(), output_np.ravel(), labels=list(range(n_classes)))
        cm += cm_

        oa = "{:.3f}".format(metrics.stats_overall_accuracy(cm))
        aa = "{:.3f}".format(metrics.stats_accuracy_per_class(cm)[0])
        t.set_postfix(OA=oa, AA=aa)

    # save the model
    torch.save(model.state_dict(), os.path.join(save_root, "state_dict.pth"))

    # write the logs
    logs.write("{} {} {} \n".format(epoch, oa, aa))
    logs.flush()

logs.close()
