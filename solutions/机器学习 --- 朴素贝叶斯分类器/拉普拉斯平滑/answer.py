import numpy as np

class NaiveBayesClassifier(object):
    def __init__(self):
        self.label_prob = {}
        self.condition_prob = {}

    def fit(self, feature, label):
        self.label_prob = {}
        self.condition_prob = {}

        n = len(label)
        n_label = len(set(label))

        # 类别概率（拉普拉斯平滑）
        for l in set(label):
            self.label_prob[l] = (np.sum(label == l) + 1) / (n + n_label)

        # 条件概率（拉普拉斯平滑）
        for l in set(label):
            self.condition_prob[l] = {}
            sub_feature = feature[label == l]
            for col in range(len(feature[0])):
                self.condition_prob[l][col] = {}
                values = set(feature[:, col])
                for v in values:
                    self.condition_prob[l][col][v] = (np.sum(sub_feature[:, col] == v) + 1) / (len(sub_feature) + len(values))

    def predict(self, feature):
        result = []
        for i, f in enumerate(feature):
            prob = np.zeros(len(self.label_prob.keys()))
            ii = 0
            for label, label_prob in self.label_prob.items():
                prob[ii] = label_prob
                for j in range(len(feature[0])):
                    prob[ii] *= self.condition_prob[label][j][f[j]]
                ii += 1
            result.append(list(self.label_prob.keys())[np.argmax(prob)])
        return np.array(result)