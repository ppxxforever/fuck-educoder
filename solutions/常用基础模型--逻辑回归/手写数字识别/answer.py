from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

def digit_predict(train_image, train_label, test_image):
    '''
    实现功能：训练模型并输出预测结果
    :param train_sample: 包含多条训练样本的样本集，类型为ndarray,shape为[-1, 8, 8]
    :param train_label: 包含多条训练样本标签的标签集，类型为ndarray
    :param test_sample: 包含多条测试样本的测试集，类型为ndarry
    :return: test_sample对应的预测标签
    '''

    #************* Begin ************#
    # 将图像数据展平为二维特征矩阵，兼容二维输入
    if train_image.ndim == 3:
        X_train = train_image.reshape(train_image.shape[0], -1)
    else:
        X_train = train_image

    if test_image.ndim == 3:
        X_test = test_image.reshape(test_image.shape[0], -1)
    else:
        X_test = test_image

    # 标准化特征
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 训练逻辑回归模型
    clf = LogisticRegression(solver='lbfgs', C=10, max_iter=5000, multi_class='multinomial')
    clf.fit(X_train_scaled, train_label)

    # 返回预测结果
    return clf.predict(X_test_scaled)
    #************* End **************#