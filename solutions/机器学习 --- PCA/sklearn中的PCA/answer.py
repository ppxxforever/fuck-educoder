from sklearn.decomposition import PCA

def cancer_predict(train_sample, train_label, test_sample):
    '''
    使用PCA降维，并进行分类，最后将分类结果返回
    :param train_sample:训练样本, 类型为ndarray
    :param train_label:训练标签, 类型为ndarray
    :param test_sample:测试样本, 类型为ndarray
    :return: 分类结果
    '''

    #********* Begin *********#
    from sklearn.linear_model import LogisticRegression

    # 用 PCA 降维
    pca = PCA(n_components=10)
    train_sample = pca.fit_transform(train_sample)
    test_sample = pca.transform(test_sample)
    # 再用分类器分类（AUC > 0.9 即可）
    clf = LogisticRegression(max_iter=1000)
    clf.fit(train_sample, train_label)
    return clf.predict(test_sample)
    #********* End *********#