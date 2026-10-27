import torch
import torch.nn as nn

########## Begin ##########
conv3_3 = nn.Conv2d(in_channels=1, out_channels=1, kernel_size=3)
print(conv3_3.kernel_size)

conv5_5 = nn.Conv2d(in_channels=1, out_channels=1, kernel_size=5)
print(conv5_5.kernel_size)

conv7_7 = nn.Conv2d(in_channels=1, out_channels=1, kernel_size=7)
print(conv7_7.kernel_size)

conv9_9 = nn.Conv2d(in_channels=1, out_channels=1, kernel_size=9)
print(conv9_9.kernel_size)

conv11_11 = nn.Conv2d(in_channels=1, out_channels=1, kernel_size=11)
print(conv11_11.kernel_size)

########## End ##########