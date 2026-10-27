import numpy as np


def calcInfoGain(feature, label, index):
    '''
    计算信息增益
    :param feature:测试用例中字典里的feature，类型为ndarray
    :param label:测试用例中字典里的label，类型为ndarray
    :param index:测试用例中字典里的index，即feature部分特征列的索引。该索引指的是feature中第几个特征，如index:0表示使用第一个特征来计算信息增益。
    :return:信息增益，类型float
    '''

    #*********** Begin ***********#
    # 计算数据集的经验熵
    def calcInfoEntropy(label):
        label_set = set(label)
        result = 0
        for l in label_set:
            count = 0
            for j in range(len(label)):
                if label[j] == l:
                    count += 1
            p = count / len(label)
            result -= p * np.log2(p)
        return result

    # 计算某个特征取值划分后的条件熵
    def calcHDA(feature, label, index, value):
        count = 0
        sub_label = []
        for i in range(len(feature)):
            if feature[i][index] == value:
                count += 1
                sub_label.append(label[i])
        pHA = count / len(feature)
        return pHA * calcInfoEntropy(sub_label)

    base_e = calcInfoEntropy(label)
    f = np.array(feature)
    f_set = set(f[:, index])
    sum_HDA = 0
    for value in f_set:
        sum_HDA += calcHDA(feature, label, index, value)
    # 信息增益 = 经验熵 - 条件熵
    return base_e - sum_HDA
    #*********** End *************#