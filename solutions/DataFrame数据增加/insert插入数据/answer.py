# 导入pandas库
import pandas as pd

# 字典
lst={'ID':[3,9,5],'Name':['陈芳','刘佳','方鸣'],
    'Marks':[85,92,65],'Grade':['B','A','D']}
# 字典lst创建DataFrame对象
df = pd.DataFrame(lst)

print('原数据\n',df)
# 在第2列插入一列，列名为age，内容为[18,19,18]
df.insert(2, 'age', [18,19,18])
print('新数据\n',df)