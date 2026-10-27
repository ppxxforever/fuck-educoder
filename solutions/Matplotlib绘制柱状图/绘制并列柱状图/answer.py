# 导入pandas库
import pandas as pd

# 导入numpy库
import numpy as np

# 导入matplotlib.pyplot库
import matplotlib.pyplot as plt

# 设黑体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 读取temperature.txt文件到对象df中
df = pd.read_csv('temperature.txt', sep='\t', encoding='utf-8')

# 取城市列
city = df['城市']

# 取温度并去掉单位
high = df['最高温度'].str.replace('℃', '').astype(float)
low = df['最低温度'].str.replace('℃', '').astype(float)

# 绘图区大小设置
plt.figure(figsize=(10, 6))

# x轴坐标
x = np.arange(len(city))

# x轴刻度与标签
plt.xticks(x - 0.2, city)

# 绘制柱状图
plt.bar(x - 0.2, high, width=0.4, label='最高温度', color='red', alpha=0.6, edgecolor='red')
plt.bar(x + 0.2, low, width=0.4, label='最高温度')

# 显示图例
plt.legend()

# 设置y轴刻度范围
plt.ylim(0, 40)

# x轴标签
plt.xlabel('城市', fontsize=14)

# y轴标签
plt.ylabel('℃', fontsize=14)

# 标题
plt.title('湖南省城市温度并列柱状图', fontsize=24)

# 保存图
plt.savefig('bar2/result/tu2.png')
