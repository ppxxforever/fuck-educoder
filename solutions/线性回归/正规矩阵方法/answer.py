import numpy as np
from sklearn.datasets import make_regression
from sklearn.model_selection import train_test_split
np.random.seed(1)


def lr(x_train, x_test, y_train, y_test):
    """
    :param x_train: 训练集
    :param x_test: 训练集标签
    :param y_train: 测试集
    :param y_test: 测试集标签
    :return: 预测值与测试集标签的均方误差
    """
    # 请根据提示在下面补全代码
    # ********** Begin ********* #
    # 使用正规方程公式求得theta
    theta = np.linalg.inv(x_train.T @ x_train) @ x_train.T @ y_train

    # 使用theta预测结果
    y_pred = x_test @ theta

    # 求出预测值与目标值的均方误差
    mse = np.mean((y_pred - y_test) ** 2)

    # ********** End ********* #
    return mse


if __name__ == '__main__':
    X, Y = make_regression(n_samples=500, n_features=1, n_targets=1, noise=1.5)
    x_train, x_test, y_train, y_test = train_test_split(X, Y)
    mse = lr(x_train, x_test, y_train, y_test)
    print(mse)
