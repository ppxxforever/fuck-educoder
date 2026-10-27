import numpy as np

def calc_JC(y_true, y_pred):
    '''
    计算并返回JC系数
    :param y_true: 参考模型给出的簇，类型为ndarray
    :param y_pred: 聚类模型给出的簇，类型为ndarray
    :return: JC系数
    '''

    #******** Begin *******#
    a = b = c = 0
    n = len(y_true)
    for i in range(n):
        for j in range(i + 1, n):
            same_true = y_true[i] == y_true[j]
            same_pred = y_pred[i] == y_pred[j]
            if same_true and same_pred:
                a += 1
            elif same_true and not same_pred:
                b += 1
            elif (not same_true) and same_pred:
                c += 1
    return a / (a + b + c)
    #******** End *******#


def calc_FM(y_true, y_pred):
    '''
    计算并返回FM指数
    :param y_true: 参考模型给出的簇，类型为ndarray
    :param y_pred: 聚类模型给出的簇，类型为ndarray
    :return: FM指数
    '''

    #******** Begin *******#
    a = b = c = 0
    n = len(y_true)
    for i in range(n):
        for j in range(i + 1, n):
            same_true = y_true[i] == y_true[j]
            same_pred = y_pred[i] == y_pred[j]
            if same_true and same_pred:
                a += 1
            elif same_true and not same_pred:
                b += 1
            elif (not same_true) and same_pred:
                c += 1
    return np.sqrt((a / (a + b)) * (a / (a + c)))
    #******** End *******#

def calc_Rand(y_true, y_pred):
    '''
    计算并返回Rand指数
    :param y_true: 参考模型给出的簇，类型为ndarray
    :param y_pred: 聚类模型给出的簇，类型为ndarray
    :return: Rand指数
    '''

    #******** Begin *******#
    a = d = 0
    n = len(y_true)
    for i in range(n):
        for j in range(i + 1, n):
            same_true = y_true[i] == y_true[j]
            same_pred = y_pred[i] == y_pred[j]
            if same_true and same_pred:
                a += 1
            elif (not same_true) and (not same_pred):
                d += 1
    return (a + d) / (n * (n - 1) / 2)
    #******** End *******#