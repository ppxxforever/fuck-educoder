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
    return 1.0 / (1.0 + np.exp(-x))


def fit(x, y, eta=1e-3, n_iters=10000):
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

    if x.ndim == 1:
        x = x.reshape(1, -1)

    # 判断是否已经添加了偏置列
    if x.shape[1] > 0 and np.allclose(x[:, 0], 1.0):
        X = x.copy()
    else:
        X = np.hstack([np.ones((x.shape[0], 1)), x])

    m, n = X.shape

    # 仅对特征列进行标准化，偏置列保持为1
    mean = np.mean(X[:, 1:], axis=0)
    std = np.std(X[:, 1:], axis=0)
    std[std == 0] = 1.0

    X_scaled = X.copy()
    X_scaled[:, 1:] = (X[:, 1:] - mean) / std

    theta = np.zeros(n)
    reg = 1e-4

    # 使用牛顿法（IRLS）快速收敛，避免长时间迭代
    max_iter = min(max(int(n_iters), 1), 30)

    reg_matrix = np.eye(n)
    reg_matrix[0, 0] = 0.0  # 不惩罚偏置项

    for _ in range(max_iter):
        z = X_scaled.dot(theta)
        a = sigmoid(z)

        weights = a * (1.0 - a)
        weights = np.clip(weights, 1e-12, None)

        gradient = X_scaled.T.dot(a - y) / m
        hessian = X_scaled.T.dot(X_scaled * weights[:, None]) / m + reg * reg_matrix

        try:
            step = np.linalg.solve(hessian + 1e-8 * np.eye(n), gradient)
        except np.linalg.LinAlgError:
            step = gradient

        # 防止完全可分时参数发散
        step = np.clip(step, -5.0, 5.0)
        theta -= step

        if np.linalg.norm(step) < 1e-8:
            break

    # 将标准化空间中的参数映射回原始特征空间
    theta_orig = np.zeros(n)
    if n > 1:
        theta_orig[0] = theta[0] - np.sum(theta[1:] * mean / std)
        theta_orig[1:] = theta[1:] / std
    else:
        theta_orig = theta

    return theta_orig


def predict(x, theta):
    '''
    预测函数
    :param x: 特征数据，类型为ndarray
    :param theta: 模型参数，类型为ndarray
    :return: 预测类别，类型为ndarray
    '''
    x = np.asarray(x, dtype=float)
    theta = np.asarray(theta, dtype=float)

    if x.ndim == 1:
        x = x.reshape(1, -1)

    if x.shape[1] == theta.shape[0] - 1:
        X = np.hstack([np.ones((x.shape[0], 1)), x])
    elif x.shape[1] == theta.shape[0]:
        X = x
    else:
        X = np.hstack([np.ones((x.shape[0], 1)), x])

    return (sigmoid(X.dot(theta)) >= 0.5).astype(int)