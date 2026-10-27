import numpy as np

def sigmoid(t):
    return 1 / (1 + np.exp(-t))