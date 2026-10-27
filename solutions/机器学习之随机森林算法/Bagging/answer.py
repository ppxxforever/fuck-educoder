import numpy as np
from collections import Counter
from sklearn.tree import DecisionTreeClassifier

class BaggingClassifier():
    def __init__(self, n_model=10):
        '''
        初始化函数
        '''
        #分类器的数量，默认为10
        self.n_model = n_model
        #用于保存模型的列表，训练好分类器后将对象append进去即可
        self.models = []


    def fit(self, feature, label):
        '''
        训练模型，请记得将模型保存至self.models
        :param feature: 训练集数据，类型为ndarray
        :param label: 训练集标签，类型为ndarray
        :return: None
        '''

        #************* Begin ************#
        for i in range(self.n_model):
            # 有放回地采样（bootstrap）
            index = np.random.choice(len(feature), len(feature), replace=True)
            clf = DecisionTreeClassifier()
            clf.fit(feature[index], label[index])
            self.models.append(clf)
        #************* End **************#


    def predict(self, feature):
        '''
        :param feature: 测试集数据，类型为ndarray
        :return: 预测结果，类型为ndarray，如np.array([0, 1, 2, 2, 1, 0])
        '''
        #************* Begin ************#
        preds = np.array([clf.predict(feature) for clf in self.models])
        result = []
        for i in range(feature.shape[0]):
            # 投票：票数最多的标签
            result.append(Counter(preds[:, i]).most_common(1)[0][0])
        return np.array(result)
        #************* End **************#