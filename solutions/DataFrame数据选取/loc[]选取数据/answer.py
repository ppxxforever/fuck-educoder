import pandas as pd

df = pd.read_excel('ClassScore.xls')
df = df.set_index('学号')

print(df.loc[2301:2302])
print(df.loc[2301:2302, ['姓名', '年龄']])
print(df.loc[[2301, 2401], ['姓名', '平时成绩']])
print(df[df['平时成绩'] > 95])
print(df[df['年龄'] == 20])