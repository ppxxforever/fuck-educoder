# 导入numpy模块
import numpy as np

# 创建一维数组[ 0  1  2  3  4  5  6  7  8  9  10 11]
arr = np.arange(12)
print(arr)

# 将一维数组创建成3行4列二维数组
arr_3x4 = arr.reshape(3, 4)
print(arr_3x4)

# 直接改变一维数组形状
arr.shape = (4, 3)
print(arr)

# 二维数组转置
arr_T = arr.T
print(arr_T)

# 二维数组展平成一维数组
arr_flat = arr_T.flatten()
print(arr_flat)