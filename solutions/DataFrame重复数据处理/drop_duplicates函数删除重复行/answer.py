# 导入pandas库
import pandas as pd

# 字典dct赋值
dct={'id':[1,2,3,1,1],'fr':['a','b','c','a','a'],'kg':[5,2,4,5,5]}
# 根据字典dct创建对象df
df=pd.DataFrame(dct)

# 查找并删除重复行，返回新对象df1
df1=df.drop_duplicates()

# 输出新对象df1
print(df1)