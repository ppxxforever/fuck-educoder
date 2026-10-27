# 导入pandas模块
import pandas as pd

# 列表lst赋值
lst = [[202301, 95, 80], [202302, 89, 75], [202303, 76, 85]]

# 从列表创建DF对象
df = pd.DataFrame(lst, columns=['学号', '语文', '数学'])

# 将DF对象写入文本文件中
df.to_csv('score.txt', sep='\t')