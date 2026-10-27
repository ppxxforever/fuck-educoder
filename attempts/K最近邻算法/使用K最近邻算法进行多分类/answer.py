# -*- coding: utf-8 -*-

from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
import numpy as np
from sklearn.neighbors import KNeighborsClassifier

samples=int(input())
classNum=int(input())
noise=float(input())

# 如果输入的噪声值大于1，按百分比处理
if noise > 1:
    noise = noise / 100.0

# 请在此添加代码 完成本关任务
#
# ********** Begin *********#
data=make_classification(n_samples=samples, n_informative=20,n_redundant=0, n_classes=classNum, flip_y=noise, random_state=0)
X,y=data
X_train, X_test, Y_train, Y_test = train_test_split(X, y, random_state=0)
clf=KNeighborsClassifier()
clf.fit(X_train, Y_train)
ans=clf.predict(X_test)
right_num=np.sum(ans == Y_test)
print(int(right_num))
# ********** End **********#