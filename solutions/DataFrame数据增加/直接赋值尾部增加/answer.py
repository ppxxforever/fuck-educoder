import pandas as pd

# 创建2行2列对象
df1=pd.DataFrame([[1,2],[3,4]])
print('原数据：')
print(df1)

# 增加一列，列名为a，数据为[5,5]
df1['a']=[5,5]

# 增加一行，行名为b，数据为[0,0,0]
df1.loc['b']=[0,0,0]

# 输出处理后数据
print('增加后数据：')
print(df1)