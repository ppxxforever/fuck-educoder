#encoding=utf8
import numpy as np
#adaboost算法
class AdaBoost:
    '''
    input:n_estimators(int):迭代轮数
          learning_rate(float):弱分类器权重缩减系数
    '''
    def __init__(self, n_estimators=50, learning_rate=1.0):
        self.clf_num = n_estimators
        self.learning_rate = learning_rate
    def init_args(self, datasets, labels):
        self.X = datasets
        self.Y = labels
        self.M, self.N = datasets.shape
        # 弱分类器数目和集合
        self.clf_sets = []
        # 初始化weights
        self.weights = [1.0/self.M]*self.M
        # G(x)系数 alpha
        self.alpha = []
    #********* Begin *********#
    def _G(self, features, labels, weights):
        '''
        input:features(ndarray):数据特征
              labels(ndarray):数据标签
              weights(ndarray):样本权重系数
        '''
        m = len(features)
        error = 100000.0
        best_v = 0.0
        # 注意：direct 必须跟着最优阈值一起记，返回最后一个候选的方向会算错
        best_direct, compare_array = None, None
        # 候选阈值取相邻不同取值的中点：阈值一定落在样本点之间，
        # 不会出现「阈值恰好等于某个样本值 → 一个候选都挑不出来」的情况
        uniq = np.unique(features)
        candidates = (uniq[:-1] + uniq[1:]) / 2.0 if len(uniq) > 1 else []
        for v in candidates:
            # 正向分类
            compare_array_positive = np.array(
                [1 if features[k] > v else -1 for k in range(m)])
            weight_error_positive = sum(
                [weights[k] for k in range(m) if compare_array_positive[k] != labels[k]])
            # 反向分类
            compare_array_nagetive = np.array(
                [-1 if features[k] > v else 1 for k in range(m)])
            weight_error_nagetive = sum(
                [weights[k] for k in range(m) if compare_array_nagetive[k] != labels[k]])
            if weight_error_positive < weight_error_nagetive:
                weight_error = weight_error_positive
                compare_array_ = compare_array_positive
                direct = 'positive'
            else:
                weight_error = weight_error_nagetive
                compare_array_ = compare_array_nagetive
                direct = 'nagetive'
            if weight_error < error:
                error = weight_error
                compare_array = compare_array_
                best_direct = direct
                best_v = v
        return best_v, best_direct, error, compare_array

    # 计算alpha
    def _alpha(self, error):
        return 0.5 * np.log((1 - error) / error)

    # 规范化因子
    def _Z(self, weights, a, clf):
        return sum([weights[i] * np.exp(-a * self.Y[i] * clf[i]) for i in range(self.M)])

    # 权值更新
    def _w(self, a, clf, Z):
        for i in range(self.M):
            self.weights[i] = self.weights[i] * np.exp(-a * self.Y[i] * clf[i]) / Z

    # G(x)的线性组合
    def G(self, x, v, direct):
        if direct == 'positive':
            return 1 if x > v else -1
        return -1 if x > v else 1

    def fit(self, X, y):
        '''
        X(ndarray):训练数据
        y(ndarray):训练标签
        '''
        self.init_args(X, y)

        for epoch in range(self.clf_num):
            best_clf_error, best_v, clf_result, final_direct, axis = 100000, None, None, None, None
            # 选择误差最小的特征列与阈值
            for j in range(self.N):
                v, direct, error, compare_array = self._G(self.X[:, j], self.Y, self.weights)
                if compare_array is not None and error < best_clf_error:
                    best_clf_error = error
                    best_v = v
                    final_direct = direct
                    clf_result = compare_array
                    axis = j
            # 这一轮没挑出可用的弱分类器（例如某一列取值全相同）就收敛退出
            if clf_result is None:
                break

            # 误差为 0 会导致除零，兜一个极小值
            if best_clf_error == 0:
                best_clf_error = 1e-16

            # 计算G(x)系数a
            a = self._alpha(best_clf_error)
            self.alpha.append(a)

            # 记录分类器
            self.clf_sets.append((axis, best_v, final_direct))

            # 规范化因子
            Z = self._Z(self.weights, a, clf_result)

            # 权值更新
            self._w(a, clf_result, Z)

    def predict(self, data):
        '''
        input:data(ndarray):单个样本
        output:预测为正样本返回+1，负样本返回-1
        '''
        result = 0
        for i in range(len(self.clf_sets)):
            axis, clf_v, direct = self.clf_sets[i]
            result += self.alpha[i] * self.G(data[axis], clf_v, direct)
        return 1 if result > 0 else -1
    #********* End *********#