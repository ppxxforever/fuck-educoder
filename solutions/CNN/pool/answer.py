import torch
from torch import nn

def pool2d(X, pool_size):
    X = X.float()
    p_h, p_w = pool_size
    Y = torch.zeros(X.shape[0] - p_h + 1, X.shape[1] - p_w + 1)
    
    ########## begin ##########
    for i in range(Y.shape[0]):
        for j in range(Y.shape[1]):
            Y[i, j] = X[i:i+p_h, j:j+p_w].max()
            
    ########## end ##########
    return Y
    
X = torch.tensor([[0, 1, 2], [3, 4, 5], [6, 7, 8]])
print(pool2d(X, (2, 2)))