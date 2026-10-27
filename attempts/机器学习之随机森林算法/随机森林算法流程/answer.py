import numpy as np

#建议代码，也算是Begin-End中的一部分
from collections import  Counter
from sklearn.tree import DecisionTreeClassifier

class RandomForestClassifier():
    def __init__(self, n_model=10):
        '''
        初始化函数
        '''
        #分类器的数量，默认为10
        self.n_model = n_model
        #用于保存模型的列表，训练好分类器后将对象append进去即可
        self.models = []
        #用于保存决策树训练时随机选取的列的索引
        self.col_indexs = []


    def fit(self, feature, label):
        '''
        训练模型
        :param feature: 训练集数据，类型为ndarray
        :param label: 训练集标签，类型为ndarray
        :return: None
        '''

        #************* Begin ************#
        feature = np.asarray(feature)
        label = np.asarray(label)
        n_samples, n_features = feature.shape
        k = max(1, int(np.log2(n_features)) if n_features > 1 else 1)
        for i in range(self.n_model):
            index = np.random.choice(n_samples, n_samples, replace=True)
            col_indexs = np.random.choice(n_features, k, replace=False)
            self.col_indexs.append(col_indexs)
            clf = DecisionTreeClassifier()
            clf.fit(feature[index][:, col_indexs], label[index])
            self.models.append(clf)
        #************* End **************#


    def predict(self, feature):
        '''
        :param feature:测试集数据，类型为ndarray
        :return:预测结果，类型为ndarray，如np.array([0, 1, 2, 2, 1, 0])
        '''
        #************* Begin ************#
        feature = np.asarray(feature)
        preds = np.array([clf.predict(feature[:, cols])
                         for clf, cols in zip(self.models, self.col_indexs)])
        result = []
        for i in range(feature.shape[0]):
            result.append(Counter(preds[:, i]).most_common(1)[0][0])
        return np.array(result)
        #************* End **************#