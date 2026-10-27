#encoding=utf8

import numpy as np

#实现核函数
def kernel(x,sigma=1.0):
    '''
    input:x(ndarray):样本
    output:x(ndarray):转化后的值
    '''    
    #********* Begin *********#
    x = np.atleast_2d(np.array(x, dtype=float))
    # 高斯（RBF）核：用样本与所有样本的核相似度代替原特征，
    # 非线性可分的数据在核空间里就线性可分了
    diff = x[:, np.newaxis, :] - x[np.newaxis, :, :]
    x = np.exp(-np.sum(diff ** 2, axis=-1) / (2.0 * sigma ** 2))
    #********* End *********#
    return x