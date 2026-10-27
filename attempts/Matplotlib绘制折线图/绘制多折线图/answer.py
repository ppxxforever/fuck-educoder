# 导入pyplot子模块
import matplotlib.pyplot as plt
# 导入pandas库
import pandas as pd
# 设中文字体为黑体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
# 读文件
data = pd.read_csv('stock.csv')
# 选取high列
high = data['high']
# 选取low列
low = data['low']
# 设置绘图区大小
plt.figure(figsize=(10, 5))
# 绘制最高价折线
plt.plot(high, label='最高价', marker='o')
# 绘制最低价折线
plt.plot(low, label='最低价', marker='*', linestyle=':')
# 显示图例
plt.legend()
# 添加图形标题
plt.title('某股票6月~7月的价格变化图', fontsize=20)
# 添加x轴标签
plt.xlabel('日期', fontsize=14)
# 添加y轴标签
plt.ylabel('元', fontsize=14)
# 保存图
plt.savefig('Z2/result/tu2.png')
