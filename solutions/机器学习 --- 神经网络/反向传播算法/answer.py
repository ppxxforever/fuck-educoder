#encoding=utf8
import os

if os.path.exists('./step2/result.csv'):
    os.remove('./step2/result.csv')
    
#********* Begin *********#
import pandas as pd
from sklearn.neural_network import MLPClassifier

train_data = pd.read_csv('./step2/train_data.csv')
train_label = pd.read_csv('./step2/train_label.csv')
train_label = train_label['target']

test_data = pd.read_csv('./step2/test_data.csv')

mlp = MLPClassifier(solver='lbfgs', max_iter=500, alpha=1e-4, hidden_layer_sizes=(20,), random_state=1)
mlp.fit(train_data, train_label)

result = mlp.predict(test_data)
# 重点：列名字必须是 result，不是 target！！
pd.DataFrame({'result': result}).to_csv('./step2/result.csv', index=False)
#********* End *********#