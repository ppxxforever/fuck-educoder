import pandas as pd

# 读文件sale.csv到对象df
df = pd.read_csv('sale.csv', index_col=0)

# 输出每个店最大值及所在月份
print("每个店最大值:")
print(df.max())
print()

print("最大值所在月份:")
print(df.idxmax())
print()

# 输出每个月总和
print("每个月之和:")
print(df.sum(axis=1))

# 输出岳麓店列平均值
print("岳麓店平均值：{:.1f}".format(df['岳麓店'].mean()))