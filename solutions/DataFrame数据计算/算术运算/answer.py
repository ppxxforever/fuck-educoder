import pandas as pd


df1 = pd.DataFrame([[1, 2, 3], [4, 5, 6]])
df2 = pd.DataFrame([[2, 4, 6], [7, 8, 9]])
df3 = pd.DataFrame([[1, 2], [3, 4]])


print("加运算:")
print(" " + str(df1 + df2))


print("乘运算:")
print(" " + str(df1 * df3))


print("乘运算:")
print(" " + str(df1.mul(df3, fill_value=0)))