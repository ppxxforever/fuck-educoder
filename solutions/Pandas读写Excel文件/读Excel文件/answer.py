# 导入pandas库
import pandas as pd

# 紧凑显示格式
pd.set_option('display.expand_frame_repr', False)
pd.set_option('display.max_rows', 10)

# 读文件
df = pd.read_excel('ClassScore.xls', index_col=0, na_values='缺考')

# 输出
print(df)