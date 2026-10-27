# 导入pandas库
import pandas as pd

# 设置最大显示10行
pd.set_option('display.max_rows', 10)

# 读文件
df = pd.read_excel('ClassScore.xls', index_col=0)

# 计算函数
def get_total(row):
    # 兼容旧版pandas，先把可能为字符串的列转换为数值，无法转换的转为NaN
    score1 = pd.to_numeric(row['平时成绩'], errors='coerce')
    score2 = pd.to_numeric(row['期末成绩'], errors='coerce')
    return 0.4 * score1 + 0.6 * score2

# 调用apply方法将计算结果增加为最后一列
df['总评成绩'] = df.apply(get_total, axis=1)

print(df)