# 导入pandas库
import pandas as pd

# 读取Score.xls文件到df对象
df = pd.read_excel('Score.xls')

# 选取对象df中期末成绩不在0~100以内的数据行，返回新的对象d0
d0 = df[(df['期末成绩'] < 0) | (df['期末成绩'] > 100)]

# 将对象d0复制到对象d1
d1 = d0.copy()

# 修改对象d1中异常值为None
mask = (d1['期末成绩'] < 0) | (d1['期末成绩'] > 100)
d1['期末成绩'] = d1['期末成绩'].astype(object)
d1.loc[mask, '期末成绩'] = None

print(d1)