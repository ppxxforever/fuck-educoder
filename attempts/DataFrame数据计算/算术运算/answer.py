# 导入pandas库
import pandas as pd


# 列表[[1,2,3],[4,5,6]]创建df1对象
df1 = pd.DataFrame([[1, 2, 3], [4, 5, 6]])


# 列表[[2,4,6],[7,8,9]]创建df2对象
df2 = pd.DataFrame([[2, 4, 6], [7, 8, 9]])


# 列表[[1,2],[3,4]]创建df3对象
df3 = pd.DataFrame([[1, 2], [3, 4]])


# df1加ddf2
print("加运算:")
print(df1 + df2)


# df1乘df3
print("乘运算:")
print(df1 * df3)


# df1乘df3，缺失值为0
print("乘运算:")
print(df1.mul(df3, fill_value=0))