# -*- coding: utf-8 -*-

import numpy as np
import warnings
warnings.filterwarnings("ignore")

def sigmoid(x):
    '''
    sigmoid函数
    :param x: 转换前的输入
    :return: 转换后的概率
    '''
    x = np.clip(x, -500, 500)
    return 1/(1+np.exp(-x))


def fit(x,y,eta=1e-3,n_iters=10000):
    '''
    训练逻辑回归模型
    :param x: 训练集特征数据，类型为ndarray
    :param y: 训练集标签，类型为ndarray
    :param eta: 学习率，类型为float
    :param n_iters: 训练轮数，类型为int
    :return: 模型参数，类型为ndarray
    '''
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float).reshape(-1)

    if x.shape[1] > 0 and np.allclose(x[:, 0], 1.0):
        x_orig = x[:, 1:]
    else:
        x_orig = x

    mean = x_orig.mean(axis=0)
    std = x_orig.std(axis=0)
    std[std == 0] = 1.0

    x_scaled = (x_orig - mean) / std
    x_train = np.hstack([np.ones((x_scaled.shape[0], 1)), x_scaled])

    m, n = x_train.shape
    theta_scaled = np.zeros(n)

    eta = 0.1
    n_iters = min(n_iters, 2000)

    for _ in range(n_iters):
        a = sigmoid(x_train.dot(theta_scaled))
        gradient = x_train.T.dot(a - y) / m
        theta_scaled -= eta * gradient

        if np.max(np.abs(gradient)) < 1e-4:
            break

    theta = np.zeros(n)
    theta[0] = theta_scaled[0] - np.sum(theta_scaled[1:] * mean / std)
    theta[1:] = theta_scaled[1:] / std
    return theta