from sklearn.model_selection import train_test_split
import numpy as np


def task():
    '''
    任务描述：使用留出法对10万条样本数据进行切分，要求对正负样本采用分层抽样保证数据的一致性，并且满足训练集占比为70%。
    '''
    data = np.random.rand(100000, 3)
    label = np.random.randint(0, 2, 100000)

    ########## Begin ##########
    train_data, test_data, train_label, test_label = train_test_split(
        data, label, test_size=0.3, stratify=label
    )
    ########## End ##########

    return train_data, test_data, train_label, test_label