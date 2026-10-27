import numpy as np

def pca(data, k):
    '''
    对data进行PCA，并将结果返回
    :param data:数据集，类型为ndarray
    :param k:想要降成几维，类型为int
    :return: 降维后的数据，类型为ndarray
    '''

    #********* Begin *********#
    # 去中心化（demean）
    data_demean = data - np.mean(data, axis=0)
    # 计算协方差矩阵（题目要求用 NumPy 的 cov）
    cov = np.cov(data_demean, rowvar=False)
    # 计算协方差矩阵的特征值与特征向量
    eig_values, eig_vectors = np.linalg.eig(cov)
    # 取实部：cov 是对称矩阵，特征值/特征向量理论上都是实数
    eig_values = np.real(eig_values)
    eig_vectors = np.real(eig_vectors)
    # 按特征值从大到小排序
    idx = np.argsort(eig_values)[::-1]
    eig_vectors = eig_vectors[:, idx]
    # 取前 k 个特征向量作为转换矩阵
    transform = eig_vectors[:, 0:k]
    # demean 后的数据与转换矩阵相乘，得到降维后的数据
    return np.dot(data_demean, transform)
    #********* End *********#