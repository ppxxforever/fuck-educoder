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
    f = np.array(feature)
    f_set = set(f[:, index])
    gini = 0.0
    for value in f_set:
        sub_label = []
        for i in range(len(feature)):
            if feature[i][index] == value:
                sub_label.append(label[i])
        # 子集的基尼值
        p_sum = 0.0
        for l in set(sub_label):
            p = sub_label.count(l) / len(sub_label)
            p_sum += p ** 2
        # 按子集样本占比加权求和
        gini += (len(sub_label) / len(feature)) * (1 - p_sum)
    return gini
    #********* End *********#