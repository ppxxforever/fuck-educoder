# 导入pandas库
import pandas as pd

# 设置DataFrame对象紧凑格式显示，最大显示6行
pd.set_option('display.max_rows', 6)

# 读ClassScore.xls文件到对象df
df = pd.read_excel('ClassScore.xls')

# 检查对象df是否为空值，并输出检查结果
print(df.isnull())

# 输出对象df每一列空值总数
print(df.isnull().sum())