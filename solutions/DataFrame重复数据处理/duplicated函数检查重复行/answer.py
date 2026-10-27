# 导入pandas库
import pandas as pd

# 字典dct赋值
dct={'id':[1,2,3,1,1],'fr':['a','b','c','a','a'],'kg':[10.5,12,14,10.5,5]}
# 根据字典dct创建对象df
df = pd.DataFrame(dct)

# 查找df重复行，返回逻辑型Series对象
dup = df.duplicated()

# 输出重复行数据
print(dup)
print('输出重复行：')
print(df[dup])