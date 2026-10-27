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
# 将 8*8 的三维图像展平为 64维二维特征
# 将8*8三维图像展平为二维64维特征
    X_train = train_image.reshape(-1, 64)
    X_test = test_image.reshape(-1, 64)
    
    # 指定saga求解器 + multinomial多分类，调高迭代次数
    model = LogisticRegression(solver='saga', multi_class='multinomial', max_iter=10000, C=0.2)
    model.fit(X_train, train_label)
    
    pred = model.predict(X_test)
    return pred
    #************* End **************#