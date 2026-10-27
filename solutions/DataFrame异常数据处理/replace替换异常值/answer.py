# 导入pandas库
import pandas as pd

# 读取ClassScore.xls文件到df对象中
df = pd.read_excel('ClassScore.xls')

# 选取对象df中期末对象为缺考的数据
result = df[df['期末成绩'] == '缺考'].copy()

# 将缺考替换成0
result['期末成绩'] = 0

# 输出替换结果
print(result)