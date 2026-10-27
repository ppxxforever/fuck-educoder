import numpy as np
import random


def _num(x):
    """把 1x1 矩阵/numpy 标量统一成 float。"""
    return x.item() if hasattr(x, 'item') else float(x)


def calcEk(oS, k):
    """
    计算误差
    Parameters：
        oS - 数据结构
        k - 标号为k的数据
    Returns:
        Ek - 标号为k的数据误差
    """
    fXk = _num(np.multiply(oS.alphas, oS.labelMat).T * (oS.X * oS.X[k, :].T) + oS.b)
    Ek = fXk - _num(oS.labelMat[k])
    return Ek


def loadDataSet(fileName):
    """
    读取数据
    Parameters:
        fileName - 文件名
    Returns:
        dataMat - 数据矩阵
        labelMat - 数据标签
    """
    dataMat = []
    labelMat = []
    fr = open(fileName)
    for line in fr.readlines():
        lineArr = line.strip().split('\t')
        dataMat.append([float(lineArr[0]), float(lineArr[1])])
        labelMat.append(float(lineArr[2]))
    return dataMat, labelMat


def selectJrand(i, m):
    """
    随机选择alpha_j的索引值
    Parameters:
        i - alpha_i的索引值
        m - alpha参数个数
    Returns:
        j - alpha_j的索引值
    """
    j = i
    while (j == i):
        j = int(random.uniform(0, m))
    return j


def selectJ(i, oS, Ei):
    """
    内循环启发方式2
    Parameters：
        i - 标号为i的数据的索引值
        oS - 数据结构
        Ei - 标号为i的数据误差
    Returns:
        j, maxK - 标号为j或maxK的数据的索引值
        Ej - 标号为j的数据误差
    """
    maxK = -1
    maxDeltaE = 0
    Ej = 0
    oS.eCache[i] = [1, Ei]
    validEcacheList = np.nonzero(oS.eCache[:, 0].A)[0]
    if (len(validEcacheList)) > 1:
        for k in validEcacheList:
            if k == i:
                continue
            Ek = calcEk(oS, k)
            deltaE = abs(Ei - Ek)
            if (deltaE > maxDeltaE):
                maxK = k
                maxDeltaE = deltaE
                Ej = Ek
        return maxK, Ej
    else:
        # 误差缓存无效时回退：为保证不同 numpy 版本下迭代次数一致，用确定性的下一个下标
        j = (i + 1) % oS.m
        Ej = calcEk(oS, j)
    return j, Ej


def updateEk(oS, k):
    """
    计算Ek,并更新误差缓存
    Parameters：
        oS - 数据结构
        k - 标号为k的数据的索引值
    Returns:
        无
    """
    Ek = calcEk(oS, k)
    oS.eCache[k] = [1, Ek]


def clipAlpha(aj, H, L):
    """
    修剪alpha_j
    Parameters:
        aj - alpha_j的值
        H - alpha上限
        L - alpha下限
    Returns:
        aj - 修剪后的alpah_j的值
    """
    if aj > H:
        aj = H
    if L > aj:
        aj = L
    return aj


class optStruct:
    """
    数据结构，维护所有需要操作的值
    Parameters：
        dataMatIn - 数据矩阵
        classLabels - 数据标签
        C - 松弛变量
        toler - 容错率
    """

    def __init__(self, dataMatIn, classLabels, C, toler):
        self.X = dataMatIn
        self.labelMat = classLabels
        self.C = C
        self.tol = toler
        self.m = np.shape(dataMatIn)[0]
        self.alphas = np.mat(np.zeros((self.m, 1)))
        self.b = 0
        self.eCache = np.mat(np.zeros((self.m, 2)))


def innerL(i, oS):
    """
    优化的SMO算法
    Parameters：
        i - 标号为i的数据的索引值
        oS - 数据结构
    Returns:
        1 - 有任意一对alpha值发生变化
        0 - 没有任意一对alpha值发生变化或变化太小
    """
    # 步骤1：计算误差Ei
    Ei = calcEk(oS, i)
    # 优化alpha，设定一定的容错率
    if ((oS.labelMat[i] * Ei < -oS.tol) and (oS.alphas[i] < oS.C)) or \
       ((oS.labelMat[i] * Ei > oS.tol) and (oS.alphas[i] > 0)):
        # 使用内循环启发方式2选择alpha_j，并计算Ej
        j, Ej = selectJ(i, oS, Ei)
        # 保存更新前的alpha值
        alphaIold = oS.alphas[i].copy()
        alphaJold = oS.alphas[j].copy()
        # 步骤2：计算上下界L和H
        if (oS.labelMat[i] != oS.labelMat[j]):
            L = max(0, oS.alphas[j] - oS.alphas[i])
            H = min(oS.C, oS.C + oS.alphas[j] - oS.alphas[i])
        else:
            L = max(0, oS.alphas[j] + oS.alphas[i] - oS.C)
            H = min(oS.C, oS.alphas[j] + oS.alphas[i])
        if L == H:
            return 0
        # 步骤3：计算eta
        eta = (2.0 * oS.X[i, :] * oS.X[j, :].T
               - oS.X[i, :] * oS.X[i, :].T
               - oS.X[j, :] * oS.X[j, :].T)
        if eta >= 0:
            return 0
        # 步骤4：更新alpha_j
        oS.alphas[j] -= oS.labelMat[j] * (Ei - Ej) / eta
        # 步骤5：修剪alpha_j
        oS.alphas[j] = clipAlpha(oS.alphas[j], H, L)
        # 更新Ej至误差缓存
        updateEk(oS, j)
        if (abs(oS.alphas[j] - alphaJold) < 0.00001):
            return 0
        # 步骤6：更新alpha_i
        oS.alphas[i] += oS.labelMat[j] * oS.labelMat[i] * (alphaJold - oS.alphas[j])
        # 更新Ei至误差缓存
        updateEk(oS, i)
        # 步骤7：更新b_1和b_2
        b1 = (oS.b - Ei
              - oS.labelMat[i] * (oS.alphas[i] - alphaIold) * oS.X[i, :] * oS.X[i, :].T
              - oS.labelMat[j] * (oS.alphas[j] - alphaJold) * oS.X[i, :] * oS.X[j, :].T)
        b2 = (oS.b - Ej
              - oS.labelMat[i] * (oS.alphas[i] - alphaIold) * oS.X[i, :] * oS.X[j, :].T
              - oS.labelMat[j] * (oS.alphas[j] - alphaJold) * oS.X[j, :] * oS.X[j, :].T)
        # 步骤8：根据b_1和b_2更新b
        if (0 < oS.alphas[i]) and (oS.C > oS.alphas[i]):
            oS.b = b1
        elif (0 < oS.alphas[j]) and (oS.C > oS.alphas[j]):
            oS.b = b2
        else:
            oS.b = (b1 + b2) / 2.0
        return 1
    return 0


def smoP(dataMatIn, classLabels, C, toler, maxIter):
    """
    完整的线性SMO算法
    Parameters：
        dataMatIn - 数据矩阵
        classLabels - 数据标签
        C - 松弛变量
        toler - 容错率
        maxIter - 最大迭代次数
    Returns:
        oS.b - SMO算法计算的b
        oS.alphas - SMO算法计算的alphas
    """
    # 初始化数据结构
    oS = optStruct(np.mat(dataMatIn), np.mat(classLabels).transpose(), C, toler)
    # 初始化当前迭代次数
    it = 0
    entireSet = True
    alphaPairsChanged = 0
    # 遍历整个数据集都alpha也没有更新或者超过最大迭代次数，则退出循环
    while (it < maxIter) and ((alphaPairsChanged > 0) or entireSet):
        alphaPairsChanged = 0
        # 遍历整个数据集
        if entireSet:
            for i in range(oS.m):
                alphaPairsChanged += innerL(i, oS)
            it += 1
        # 遍历非边界值
        else:
            nonBoundIs = np.nonzero((oS.alphas.A > 0) * (oS.alphas.A < C))[0]
            for i in nonBoundIs:
                alphaPairsChanged += innerL(i, oS)
            it += 1
        # 遍历一次后改为非边界遍历
        if entireSet:
            entireSet = False
        elif alphaPairsChanged == 0:
            entireSet = True
    print("迭代次数: %d" % it)
    return oS.b, oS.alphas


def calcWs(alphas, dataArr, classLabels):
    """
    计算w
    Parameters:
        dataArr - 数据矩阵
        classLabels - 数据标签
        alphas - alphas值
    Returns:
        w - 计算得到的w
    """
    X = np.mat(dataArr)
    labelMat = np.mat(classLabels).transpose()
    m, n = np.shape(X)
    w = np.zeros((n, 1))
    for i in range(m):
        w += np.multiply(alphas[i] * labelMat[i], X[i, :].T)
    return w


if __name__ == '__main__':
    dataArr, classLabels = loadDataSet('./src/step2/testSet.txt')
    b, alphas = smoP(dataArr, classLabels, 0.6, 0.001, 40)
    w = calcWs(alphas, dataArr, classLabels)
