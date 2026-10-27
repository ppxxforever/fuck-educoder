# -*- coding: utf-8 -*-

from sklearn.datasets import make_blobs
import numpy as np
from sklearn.neighbors import KNeighborsClassifier


samples = int(input())
random_state = int(input())

# 请在此添加代码 完成本关任务
#
# ********** Begin *********#

x1 = float(input())
x2 = float(input())
X, y = make_blobs(n_samples=samples, random_state=random_state)
clf = KNeighborsClassifier()
clf.fit(X, y)
print(clf.predict([[x1, x2]]).tolist())

# ********** End **********#