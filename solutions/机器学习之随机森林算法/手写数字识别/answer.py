from sklearn.ensemble import RandomForestClassifier

def digit_predict(train_image, train_label, test_image):
    '''
    实现功能：训练模型并输出预测结果
    :param train_image: 包含多条训练样本的样本集，类型为ndarray,shape为[-1, 8, 8]
    :param train_label: 包含多条训练样本标签的标签集，类型为ndarray
    :param test_image: 包含多条测试样本的测试集，类型为ndarry
    :return: test_image对应的预测标签，类型为ndarray
    '''

    #************* Begin ************#
    train_image = train_image.reshape(train_image.shape[0], -1)
    test_image = test_image.reshape(test_image.shape[0], -1)

    clf = RandomForestClassifier(n_estimators=500, criterion='entropy', max_features='sqrt', random_state=42)
    clf.fit(train_image, train_label)
    return clf.predict(test_image)
    #************* End **************#