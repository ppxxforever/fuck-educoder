# 导入OpenCV库和NumPy库
import cv2
import numpy as np

np.random.seed(1477)

# 读取图像文件
img = cv2.imread('src/step1/lnt2.png')

# 将彩色图像转换为灰度图像
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # 将图片二值化，彩色图片该方法无法做分割
img = gray

# 图像类型转换为float64，max_iter为200
#********* Begin *********#
img_double = np.array(img, dtype=np.float64)
cluster_num = 2

max_iter = 200

# 随机初始化标签
label = np.random.randint(1, cluster_num + 1, img.shape)
#********* End *********#

iter = 0

# 定义卷积核
f_u = np.array([0, 1, 0, 0, 0, 0, 0, 0, 0]).reshape(3, 3)
f_d = np.array([0, 0, 0, 0, 0, 0, 0, 1, 0]).reshape(3, 3)
f_l = np.array([0, 0, 0, 1, 0, 0, 0, 0, 0]).reshape(3, 3)
f_r = np.array([0, 0, 0, 0, 0, 1, 0, 0, 0]).reshape(3, 3)
f_ul = np.array([1, 0, 0, 0, 0, 0, 0, 0, 0]).reshape(3, 3)
f_ur = np.array([0, 0, 1, 0, 0, 0, 0, 0, 0]).reshape(3, 3)
f_dl = np.array([0, 0, 0, 0, 0, 0, 1, 0, 0]).reshape(3, 3)
f_dr = np.array([0, 0, 0, 0, 0, 0, 0, 0, 1]).reshape(3, 3)

while iter < max_iter:
    iter = iter + 1
    print('iter:', iter)

    # 使用卷积进行标签更新
    label_u = cv2.filter2D(np.array(label, dtype=np.uint8), -1, f_u)
    label_d = cv2.filter2D(np.array(label, dtype=np.uint8), -1, f_d)
    label_l = cv2.filter2D(np.array(label, dtype=np.uint8), -1, f_l)
    label_r = cv2.filter2D(np.array(label, dtype=np.uint8), -1, f_r)
    label_ul = cv2.filter2D(np.array(label, dtype=np.uint8), -1, f_ul)
    label_ur = cv2.filter2D(np.array(label, dtype=np.uint8), -1, f_ur)
    label_dl = cv2.filter2D(np.array(label, dtype=np.uint8), -1, f_dl)
    label_dr = cv2.filter2D(np.array(label, dtype=np.uint8), -1, f_dr)
    m, n = label.shape
    p_c = np.zeros((cluster_num, m, n))

    # 计算每个类别的先验概率
    for i in range(cluster_num):
        label_i = (i + 1) * np.ones((m, n))
        u_T = 1 * np.logical_not(label_i - label_u)
        d_T = 1 * np.logical_not(label_i - label_d)
        l_T = 1 * np.logical_not(label_i - label_l)
        r_T = 1 * np.logical_not(label_i - label_r)
        ul_T = 1 * np.logical_not(label_i - label_ul)
        ur_T = 1 * np.logical_not(label_i - label_ur)
        dl_T = 1 * np.logical_not(label_i - label_dl)
        dr_T = 1 * np.logical_not(label_i - label_dr)
        temp = u_T + d_T + l_T + r_T + ul_T + ur_T + dl_T + dr_T

        p_c[i, :] = (1.0 / 8) * temp

    p_c[p_c == 0] = 0.001

    mu = np.zeros((1, cluster_num))
    sigma = np.zeros((1, cluster_num))

    # 估计每个类别的均值和方差
    #********* Begin *********#
    for i in range(cluster_num):
        index = (label == i + 1)
        data_c = img_double[index]
        mu[0, i] = data_c.mean()
        sigma[0, i] = data_c.var()
    #********* End *********#

    p_sc = np.zeros((cluster_num, m, n))
    one_a = np.ones((m, n))

    # 计算每个类别的后验概率
    for j in range(cluster_num):
        MU = mu[0, j] * one_a
        p_sc[j, :] = (1.0 / np.sqrt(2 * np.pi * sigma[0, j])) * np.exp(-1. * ((img - MU) ** 2) / (2 * sigma[0, j]))

    X_out = np.log(p_c) + np.log(p_sc)
    label_c = X_out.reshape(2, m * n)
    label_c_t = label_c.T
    label_m = np.argmax(label_c_t, axis=1)
    label_m = label_m + np.ones(label_m.shape)  # 由于上一步返回的是index下标，与label其实就差1，因此加上一个ones矩阵即可
    label = label_m.reshape(m, n)

label = label - np.ones(label.shape)  # 为了出现0
lable_w = 255 * label  # 此处做法只能显示两类，一类用0表示另一类用255表示

cv2.imwrite('src/step1/stu_img/lnt_re.jpg', lable_w)