# 导入pyplot子模块
import matplotlib.pyplot as plt
# 导入pandas库
import pandas as pd
# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
# 读文件
df = pd.read_csv('eqList2022.csv')
# 取深度列
depth = df['深度']
# 取震级列
mag = df['震级']
# 绘制散点图
plt.scatter(depth, mag)
# 添加x轴标签
plt.xlabel('震源深度(km)', fontsize=14)
# 添加y轴标签
plt.ylabel('地震级别', fontsize=14)
# 添加图标题
plt.title('2022年全球地震深度与震级散点图', fontsize=24)
# 保存图
plt.savefig('sc1/result/tu1.png')
