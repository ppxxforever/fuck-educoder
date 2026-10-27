import torch
import torch.nn as nn

X = torch.arange(16, dtype=torch.float).view((1, 1, 4, 4))

print("原矩阵为：")
print(X)

########## Begin ##########
pool2d = nn.MaxPool2d(kernel_size=3, stride=1)

########## End ##########

print("最大池化后的矩阵为：")
print(pool2d(X))