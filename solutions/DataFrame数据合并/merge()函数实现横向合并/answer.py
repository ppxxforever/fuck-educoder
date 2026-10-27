import pandas as pd

# 定义对象df1和df2
df1=pd.DataFrame({'学号':[1,2,3,1,2,3],'成绩':[73,74,80,87,85,86]})
df2=pd.DataFrame({'学号':[1,2,3],'性别':['男','女','男']})
# 按学号合并df1和df2
df3=pd.merge(df1,df2,on='学号')
df3=df3.sort_values(by='学号',kind='mergesort').reset_index(drop=True)
print(df3)