from sklearn.linear_model import LogisticRegression

def digit_predict(train_image, train_label, test_image):
    '''
    实现功能：训练模型并输出预测结果
    :param train_sample: 包含多条训练样本的样本集，类型为ndarray,shape为[-1, 8, 8]
    :param train_label: 包含多条训练样本标签的标签集，类型为ndarray
    :param test_sample: 包含多条测试样本的测试集，类型为ndarry
    :return: test_sample对应的预测标签
    '''

    #************* Begin ************#
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import GridSearchCV

    # 将图像数据展平为二维特征矩阵，兼容二维输入
    if train_image.ndim == 3:
        X_train = train_image.reshape(train_image.shape[0], -1)
    else:
        X_train = train_image

    if test_image.ndim == 3:
        X_test = test_image.reshape(test_image.shape[0], -1)
    else:
        X_test = test_image

    # 构建标准化与逻辑回归流水线，通过交叉验证选择较优参数
    pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('logreg', LogisticRegression(max_iter=5000, multi_class='auto'))
    ])

    param_grid = {
        'logreg__C': [0.001, 0.01, 0.1, 1, 10, 100],
        'logreg__solver': ['lbfgs', 'saga', 'liblinear'],
    }

    search = GridSearchCV(pipe, param_grid, cv=5, scoring='accuracy')
    search.fit(X_train, train_label)

    return search.predict(X_test)
    #************* End **************#