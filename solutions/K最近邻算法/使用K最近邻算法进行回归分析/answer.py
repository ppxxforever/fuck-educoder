# -*- coding: utf-8 -*-

import numpy as np
from sklearn.neighbors import KNeighborsRegressor


def getRegressor(X, y):
    # 请在此添加代码 完成本关任务
    #
    # ********** Begin *********#
    reg = KNeighborsRegressor(n_neighbors=1)
    reg.fit(X, y)
    return reg
    # ********** End **********#
