#encoding=utf8
from sklearn.ensemble import AdaBoostClassifier

def ada_classifier(train_data,train_label,test_data):
    '''
    input:train_data(ndarray):训练数据
          train_label(ndarray):训练标签
          test_data(ndarray):测试标签
    output:predict(ndarray):预测结果
    '''
    #********* Begin *********#
    clf = AdaBoostClassifier(n_estimators=200, learning_rate=0.5, random_state=42)
    clf.fit(train_data, train_label)
    predict = clf.predict(test_data)
    #********* End *********# 
    return predict