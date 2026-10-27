import pandas as pd


# 创建对象
lst={'ID':[3,9,5],'Name':['陈芳','刘佳','方鸣'],
     'Marks':[85,58,55],'Grade':['B','A','D']}
df=pd.DataFrame(lst)
print('原数据:\n',df)
# 删除第0行
print('删除第0行:\n',df.drop(0))


# 删除Grade列
print('删除Grade列:\n',df.drop('Grade',axis=1))


# 删除Marks小于60的行
print('删除Marks小于60的行:\n',df.drop(df[df['Marks']<60].index))