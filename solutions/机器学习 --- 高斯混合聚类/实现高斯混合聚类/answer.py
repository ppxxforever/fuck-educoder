import numpy as np
from scipy.stats import multivariate_normal

class GMM(object):
    def __init__(self, n_components, max_iter=100):
        '''
        构造函数
        :param n_components: 想要划分成几个簇，类型为int
        :param max_iter: EM的最大迭代次数
        '''
        self.n_components = n_components
        self.max_iter = max_iter

    def fit(self, train_data):
        '''
        训练，将模型参数分别保存至self.alpha，self.mu，self.sigma中
        :param train_data: 训练数据集，类型为ndarray
        :return: 无返回
        '''
        row, col = train_data.shape
        # 初始化每个高斯分布的响应系数
        self.alpha = np.array([1.0 / self.n_components] * self.n_components)
        # 初始化每个高斯分布的均值向量
        self.mu = np.random.rand(self.n_components, col)
        # 初始化每个高斯分布的协方差矩阵
        self.sigma = np.array([np.eye(col)] * self.n_components)

        #********* Begin *******#
        # EM 迭代
        for _ in range(self.max_iter):
            # E 步：每个样本由每个高斯分布生成的后验概率（响应度）
            gamma = np.zeros((row, self.n_components))
            for k in range(self.n_components):
                gamma[:, k] = self.alpha[k] * multivariate_normal(
                    mean=self.mu[k], cov=self.sigma[k]).pdf(train_data)
            gamma_sum = gamma.sum(axis=1, keepdims=True)
            gamma_sum[gamma_sum == 0] = 1e-300
            gamma = gamma / gamma_sum

            # M 步：更新 alpha、mu、sigma
            Nk = gamma.sum(axis=0)
            for k in range(self.n_components):
                self.mu[k] = (gamma[:, k] @ train_data) / Nk[k]
                diff = train_data - self.mu[k]
                self.sigma[k] = (gamma[:, k][:, np.newaxis] * diff).T @ diff / Nk[k]
                # 防止协方差矩阵退化
                self.sigma[k] += np.eye(col) * 1e-6
                self.alpha[k] = Nk[k] / row
        #********* End *********#


    def predict(self, test_data):
        '''
        预测，根据训练好的模型参数将test_data进行划分。
        注意：划分的标签的取值范围为[0,self.n_components-1]，即若self.n_components为3，则划分的标签的可能取值为0,1,2。
        :param test_data: 测试集数据，类型为ndarray
        :return: 划分结果，类型为你ndarray
        '''

        #********* Begin *********#
        prob = np.zeros((test_data.shape[0], self.n_components))
        for k in range(self.n_components):
            prob[:, k] = self.alpha[k] * multivariate_normal(
                mean=self.mu[k], cov=self.sigma[k]).pdf(test_data)
        # 取后验概率最大的簇作为划分结果，标签范围 [0, n_components-1]
        return np.argmax(prob, axis=1)
        #********* End *********#