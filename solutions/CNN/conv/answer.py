import torch 
from torch import nn

# 定义二维卷积函数
def corr2d(X, K):  
    h, w = K.shape
    # 输出矩阵Y
    Y = torch.zeros((X.shape[0] - h + 1, X.shape[1] - w + 1))
    ########## begin ##########
    for i in range(Y.shape[0]):
        for j in range(Y.shape[1]):
            Y[i, j] = (X[i:i+h, j:j+w] * K).sum()
    ########## end ##########
    return Y
    

# 输入矩阵X与核矩阵K
X = torch.tensor([[0, 1, 2], [3, 4, 5], [6, 7, 8]])
K = torch.tensor([[0, 1], [2, 3]])
print(corr2d(X, K))