# 导入pandas库
import pandas as pd

# 字典lst
lst={'ID':[3,9,5],'Name':['陈芳','刘佳','方鸣'],
'Marks':[85,92,65],'Grade':['B','A','D']}
# 根据字典lst创建对象
df = pd.DataFrame(lst)
# 设ID列为行索引
df = df.set_index('ID')
# 按行索引升序排列
df = df.sort_index()

print(df)