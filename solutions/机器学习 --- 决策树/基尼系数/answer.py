import numpy as np

def calcGini(feature, label, index):
    '''
    计算基尼系数
    :param feature:测试用例中字典里的feature，类型为ndarray
    :param label:测试用例中字典里的label，类型为ndarray
    :param index:测试用例中字典里的index，即feature部分特征列的索引。该索引指的是feature中第几个特征，如index:0表示使用第一个特征来计算信息增益。
    :return:基尼系数，类型float
    '''

    #********* Begin *********#
    feature = np.array(feature)
    label = np.array(label)
    f_set = set(feature[:, index])
    gini = 0.0
    for value in f_set:
        sub_label = label[feature[:, index] == value]
        p_sum = 0.0
        for l in set(sub_label):
            p = np.sum(sub_label == l) / len(sub_label)
            p_sum += p ** 2
        gini += (len(sub_label) / len(feature)) * (1 - p_sum)
    return gini
    #********* End *********#