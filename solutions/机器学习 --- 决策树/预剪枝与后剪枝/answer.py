import numpy as np
from copy import deepcopy

class DecisionTree(object):
    def __init__(self):
        self.tree = {}

    def calcInfoGain(self, feature, label, index):
        def calcInfoEntropy(feature, label):
            label_set = set(label)
            result = 0
            for l in label_set:
                count = 0
                for j in range(len(label)):
                    if label[j] == l:
                        count += 1
                p = count / len(label)
                result -= p * np.log2(p)
            return result

        def calcHDA(feature, label, index, value):
            count = 0
            sub_feature = []
            sub_label = []
            for i in range(len(feature)):
                if feature[i][index] == value:
                    count += 1
                    sub_feature.append(feature[i])
                    sub_label.append(label[i])
            pHA = count / len(feature)
            e = calcInfoEntropy(sub_feature, sub_label)
            return pHA * e

        base_e = calcInfoEntropy(feature, label)
        f = np.array(feature)
        f_set = set(f[:, index])
        sum_HDA = 0
        for value in f_set:
            sum_HDA += calcHDA(feature, label, index, value)
        return base_e - sum_HDA

    def getBestFeature(self, feature, label):
        max_infogain = 0
        best_feature = 0
        for i in range(len(feature[0])):
            infogain = self.calcInfoGain(feature, label, i)
            if infogain > max_infogain:
                max_infogain = infogain
                best_feature = i
        return best_feature

    def _majority(self, tree):
        if not isinstance(tree, dict):
            return tree
        vote = {}
        def collect(node):
            if not isinstance(node, dict):
                vote[node] = vote.get(node, 0) + 1
                return
            for key in node:
                collect(node[key])
        collect(tree)
        return max(vote.items(), key=lambda x: x[1])[0]

    def calc_acc_val(self, the_tree, val_feature, val_label):
        result = []
        def classify(tree, feature):
            if not isinstance(tree, dict):
                return tree
            t_index, t_value = list(tree.items())[0]
            f_value = feature[t_index]
            if isinstance(t_value, dict):
                if f_value in t_value:
                    return classify(t_value[f_value], feature)
                else:
                    return self._majority(t_value)
            else:
                return t_value
        for f in val_feature:
            result.append(classify(the_tree, f))
        result = np.array(result)
        return np.mean(result == val_label)

    def createTree(self, train_feature, train_label):
        if len(set(train_label)) == 1:
            return train_label[0]
        if len(train_feature[0]) == 1 or len(np.unique(train_feature, axis=0)) == 1:
            vote = {}
            for l in train_label:
                if l in vote.keys():
                    vote[l] += 1
                else:
                    vote[l] = 1
            max_count = 0
            vote_label = None
            for k, v in vote.items():
                if v > max_count:
                    max_count = v
                    vote_label = k
            return vote_label

        best_feature = self.getBestFeature(train_feature, train_label)
        tree = {best_feature: {}}
        f = np.array(train_feature)
        f_set = set(f[:, best_feature])
        for v in f_set:
            sub_feature = []
            sub_label = []
            for i in range(len(train_feature)):
                if train_feature[i][best_feature] == v:
                    sub_feature.append(train_feature[i])
                    sub_label.append(train_label[i])
            tree[best_feature][v] = self.createTree(sub_feature, sub_label)
        return tree

    def post_cut(self, val_feature, val_label):
        if not isinstance(self.tree, dict):
            return

        def get_non_leaf_node_count(tree):
            non_leaf_node_path = []
            def dfs(tree, path, all_path):
                for k in tree.keys():
                    if isinstance(tree[k], dict):
                        path.append(k)
                        dfs(tree[k], path, all_path)
                        if len(path) > 0:
                            path.pop()
                    else:
                        all_path.append(path[:])
            dfs(tree, [], non_leaf_node_path)
            unique_non_leaf_node = []
            for path in non_leaf_node_path:
                isFind = False
                for p in unique_non_leaf_node:
                    if path == p:
                        isFind = True
                        break
                if not isFind:
                    unique_non_leaf_node.append(path)
            return len(unique_non_leaf_node)

        def get_the_most_deep_path(tree):
            non_leaf_node_path = []
            def dfs(tree, path, all_path):
                for k in tree.keys():
                    if isinstance(tree[k], dict):
                        path.append(k)
                        dfs(tree[k], path, all_path)
                        if len(path) > 0:
                            path.pop()
                    else:
                        all_path.append(path[:])
            dfs(tree, [], non_leaf_node_path)
            max_depth = 0
            result = None
            for path in non_leaf_node_path:
                if len(path) > max_depth:
                    max_depth = len(path)
                    result = path
            return result

        def set_vote_label(tree, path, label):
            for i in range(len(path)-1):
                tree = tree[path[i]]
            tree[path[len(path)-1]] = label

        acc_before_cut = self.calc_acc_val(self.tree, val_feature, val_label)
        non_leaf_count = get_non_leaf_node_count(self.tree)
        for _ in range(non_leaf_count):
            path = get_the_most_deep_path(self.tree)
            if path is None:
                break
            tree = deepcopy(self.tree)
            step = deepcopy(tree)
            for k in path:
                step = step[k]
            vote = {}
            def collect_votes(node):
                if not isinstance(node, dict):
                    if node in vote:
                        vote[node] += 1
                    else:
                        vote[node] = 1
                    return
                for k in node.keys():
                    collect_votes(node[k])
            collect_votes(step)
            vote_label = max(vote.items(), key=lambda item: item[1])[0]
            set_vote_label(tree, path, vote_label)
            acc_after_cut = self.calc_acc_val(tree, val_feature, val_label)
            if acc_after_cut >= acc_before_cut:
                set_vote_label(self.tree, path, vote_label)
                acc_before_cut = acc_after_cut

    def fit(self, train_feature, train_label, val_feature, val_label):
        self.tree = self.createTree(train_feature, train_label)
        self.post_cut(val_feature, val_label)

    def predict(self, feature):
        def classify(tree, f):
            if not isinstance(tree, dict):
                return tree
            t_index, t_value = list(tree.items())[0]
            f_value = f[t_index]
            if isinstance(t_value, dict):
                if f_value in t_value:
                    return classify(t_value[f_value], f)
                else:
                    return self._majority(t_value)
            else:
                return t_value
        result = []
        for f in feature:
            result.append(classify(self.tree, f))
        return np.array(result)