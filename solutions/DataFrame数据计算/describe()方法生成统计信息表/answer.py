# 导入pandas库
import pandas as pd

# 读取save.csv文件到对象df中，其中第0列为行标签
try:
    df = pd.read_csv('sale.csv', index_col=0)
except FileNotFoundError:
    df = pd.read_csv('save.csv', index_col=0)

# 调用describe()方法统计信息表v
v = df.describe()

# 将对象v写入salecount.csv文件中
v.to_csv('salecount.csv')