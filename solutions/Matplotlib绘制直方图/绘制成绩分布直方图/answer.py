# 导入pyplot子模块
import matplotlib.pyplot as plt

# 导入pandas库
import pandas as pd

# 设中文字体为黑体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 读文件
df = pd.read_excel('ClassScore.xls')

# 选取期末成绩列
score = df['期末成绩']

# 删除缺考行
score = pd.to_numeric(score, errors='coerce').dropna()

# 绘制直方图
plt.hist(score, bins=range(0, 101, 10))

# 添加x轴标签
plt.xlabel('分数')

# 添加y轴标签
plt.ylabel('人数')

# 添加图形标题
plt.title('某课程期末成绩分布图', fontsize=20)

# 保存图
plt.savefig('f1/result/tu1.png')
