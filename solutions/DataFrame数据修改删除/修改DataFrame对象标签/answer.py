# 导入pandas库
import pandas as pd

lst={'ID':[3,9,5],'Name':['陈芳','刘佳','方鸣'],
'Marks':[85,92,65],'Grade':['B','A','D']}
# 根据字典lst创建df对象，索引index=['a','b','c']
df = pd.DataFrame(lst, index=['a','b','c'])
print(df)

# 修改行标签index={'a':'00','b':'11','c':'22'}
df.rename(index={'a':'00','b':'11','c':'22'}, inplace=True)

# 修改列标签为对应小写
df.rename(columns={'ID':'id','Name':'name','Marks':'marks','Grade':'grade'}, inplace=True)

print('修改标签后数据\n',df)