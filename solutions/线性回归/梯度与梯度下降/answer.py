from sklearn.datasets import make_regression
import numpy as np
from sklearn.model_selection import train_test_split
np.random.seed(10)


def cost(theta, x, y):
    cost = np.sum((theta.dot(x.T) - y) ** 2) / 2
    return cost


def lr(x, y, alpha=0.0005, iterations=50000):
    """
    :param x:特征值
    :param y:目标值
    :param alpha:学习率
    :param iterations:迭代次数
    :return:
    """


    # ********** Begin ********** #
    # 生成随机的theta
    theta = np.random.randn(x.shape[1])

    # 学习率与迭代次数请根据实际情况进行调整
    # 通过循环不断更新theta
    m = x.shape[0]
    for _ in range(iterations):
        # 计算theta的差值
        d_theta = x.T.dot(theta.dot(x.T) - y) / m

        # 将前面的theta减去theta的差值得到新的学习率
        theta = theta - alpha * d_theta

    # ********** End ********** #
    
    return theta