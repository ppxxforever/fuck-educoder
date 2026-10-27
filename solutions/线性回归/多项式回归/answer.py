import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.model_selection import train_test_split
np.random.seed(100)


def genY(x):
    a0, a1, a2, a3, e = 0.01, -0.2, 0.3, -0.04, 0.05
    yr = a0 + a1 * x + a2 * (x ** 2) + a3 * (x ** 3) + e
    y = yr + 0.03 * np.random.rand(1)
    return y


def model_train(x, y):
    # ********** Begin ********** #
    # 利用PolynomialFeatures类构造多项式的数据，并设置最高次为3
    transfer = PolynomialFeatures(degree=3, include_bias=False)
    x = transfer.fit_transform(x)

    # 将特征值拆分成训练集和测试集
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2)

    # 实例化出一个线性回归分类器
    lr = LinearRegression()

    # 传入训练数据训练模型
    lr.fit(x_train, y_train)

    # 使用score函数对模型进行评估
    score = lr.score(x_test, y_test)

    # ********** End ********** #
    return score


if __name__ == '__main__':
    # 利用np中的linspace生成线性数据
    x = np.linspace(-1, 1, 200)
    # 用公式算出y
    y = [genY(a) for a in x]
    x = x.reshape(-1, 1)
    y = np.array(y).reshape(-1, 1)
    print(model_train(x,y ))