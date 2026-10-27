# 导入numpy模块
import numpy as np

# 根据列表[2,3,4]创建成一维数组
arr = np.array([2, 3, 4])

# 平方运算
square = arr ** 2
print(square)

# 立方运算
cube = arr ** 3
print(cube)

# 求自然对数，并保留3位小数
log_arr = np.round(np.log(arr), 3)
print(log_arr)