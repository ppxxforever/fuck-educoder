import numpy as np

def alcohol_mean(data):
    '''
    返回红酒数据中红酒的酒精平均含量
    :param data: 红酒数据对象
    :return: 酒精平均含量，类型为float
    '''

    #********* Begin *********#
    alcohol_data = data.data[:,0]
    mean_val = np.mean(alcohol_data)
    return float(mean_val)
    #********* End **********#