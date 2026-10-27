import numpy as np


class NaiveBayesClassifier(object):
    def __init__(self):
        '''
        self.label_prob表示每种类别在数据中出现的概率
        例如，{0:0.333, 1:0.667}表示数据中类别0出现的概率为0.333，类别1的概率为0.667
        '''
        self.label_prob = {}
        '''
        self.condition_prob表示每种类别确定的条件下各个特征出现的概率
        例如训练数据集中的特征为 [[2, 1, 1],
                              [1, 2, 2],
                              [2, 2, 2],
                              [2, 1, 2],
                              [1, 2, 3]]
        标签为[1, 0, 1, 0, 1]
        那么当标签为0时第0列的值为1的概率为0.5，值为2的概率为0.5;
        当标签为0时第1列的值为1的概率为0.5，值为2的概率为0.5;
        当标签为0时第2列的值为1的概率为0，值为2的概率为1，值为3的概率为0;
        当标签为1时第0列的值为1的概率为0.333，值为2的概率为0.666;
        当标签为1时第1列的值为1的概率为0.333，值为2的概率为0.666;
        当标签为1时第2列的值为1的概率为0.333，值为2的概率为0.333,值为3的概率为0.333;
        因此self.label_prob的值如下：     
        {
            0:{
                0:{
                    1:0.5
                    2:0.5
                }
                1:{
                    1:0.5
                    2:0.5
                }
                2:{
                    1:0
                    2:1
                    3:0
                }
            }
            1:
            {
                0:{
                    1:0.333
                    2:0.666
                }
                1:{
                    1:0.333
                    2:0.666
                }
                2:{
                    1:0.333
                    2:0.333
                    3:0.333
                }
            }
        }
        '''
        self.condition_prob = {}
    def fit(self, feature, label):
        '''
        对模型进行训练，需要将各种概率分别保存在self.label_prob和self.condition_prob中
        :param feature: 训练数据集所有特征组成的ndarray
        :param label:训练数据集中所有标签组成的ndarray
        :return: 无返回
        '''


        #********* Begin *********#
        self.label_prob = {}
        self.condition_prob = {}

        # 每种类别出现的概率
        for l in set(label):
            self.label_prob[l] = np.sum(label == l) / len(label)

        # 每种类别下、每个特征取每个值的概率
        for l in set(label):
            self.condition_prob[l] = {}
            sub_feature = feature[label == l]
            for col in range(len(feature[0])):
                self.condition_prob[l][col] = {}
                for v in set(feature[:, col]):
                    self.condition_prob[l][col][v] = np.sum(sub_feature[:, col] == v) / len(sub_feature)
        #********* End *********#


    def predict(self, feature):
        '''
        对数据进行预测，返回预测结果
        :param feature:测试数据集所有特征组成的ndarray
        :return:
        '''
        # ********* Begin *********#
        result = []
        for f in feature:
            prob = {}
            for l in self.label_prob:
                p = self.label_prob[l]
                for col in range(len(f)):
                    p *= self.condition_prob[l][col].get(f[col], 0)
                prob[l] = p
            # 取概率最大的类别
            result.append(max(prob, key=prob.get))
        return np.array(result)
        #********* End *********#