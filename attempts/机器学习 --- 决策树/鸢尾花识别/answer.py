#********* Begin *********#
import pandas as pd
from sklearn.tree import DecisionTreeClassifier

# 读取数据并把 DataFrame 转成 ndarray
train_data = pd.read_csv('./step7/train_data.csv').values
train_label = pd.read_csv('./step7/train_label.csv').values.ravel()
test_data = pd.read_csv('./step7/test_data.csv').values

clf = DecisionTreeClassifier(criterion='gini', max_depth=5, random_state=0)
clf.fit(train_data, train_label)
predict = clf.predict(test_data)

# 结果写回，格式与标签文件一致（单列 target，无索引）
pd.DataFrame(predict, columns=['target']).to_csv('./step7/predict.csv', index=False)
#********* End *********#