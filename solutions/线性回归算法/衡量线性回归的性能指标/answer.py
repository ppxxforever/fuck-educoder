# -*- coding: utf-8 -*-
import numpy as np

# mse
def mse_score(y_predict, y_test):
    mse = np.mean((y_predict - y_test) ** 2)
    return mse

# rmse
def rmse_score(y_predict, y_test):
    rmse = np.sqrt(mse_score(y_predict, y_test))
    return rmse

# mae
def mae_score(y_predict, y_test):
    mae = np.mean(np.abs(y_predict - y_test))
    return mae

# r2
def r2_score(y_predict, y_test):
    '''
    input:y_predict(ndarray):预测值
          y_test(ndarray):真实值
    output:r2(float):r2值
    '''
    ss_res = np.sum((y_predict - y_test) ** 2)
    ss_tot = np.sum((y_test - np.mean(y_test)) ** 2)
    r2 = 1 - ss_res / ss_tot
    return r2

class LinearRegression:
    def __init__(self):
        '''初始化线性回归模型'''
        self.theta = None

    def fit_normal(self, train_data, train_label):
        '''
        input:train_data(ndarray):训练样本
              train_label(ndarray):训练标签
        '''
        X = np.hstack([np.ones((train_data.shape[0], 1)), train_data])
        self.theta = np.linalg.inv(X.T.dot(X)).dot(X.T).dot(train_label)
        return self

    def predict(self, test_data):
        '''
        input:test_data(ndarray):测试样本
        '''
        X = np.hstack([np.ones((test_data.shape[0], 1)), test_data])
        return X.dot(self.theta)