# 导入pandas库
import pandas as pd

df1=pd.DataFrame({'学号':[1,2,3,4,5,6],'成绩':[73,74,80,87,85,86]})
df2=pd.DataFrame({'学号':[1,2,3],'性别':['男','女','男']})
# df1设置“学号”为新的索引
df1.set_index('学号', inplace=True)

# df2设置“学号”为新的索引
df2.set_index('学号', inplace=True)

# df1和df2对象按学号合并
result = pd.merge(df1, df2, left_index=True, right_index=True, how='left')
print(result)