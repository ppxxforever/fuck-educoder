# 导入pyplot子模块
import matplotlib.pyplot as plt

# 导入pandas库
import pandas as pd

# 绘制柱状图
data = pd.DataFrame({'x': [0, 1, 2, 3, 4], 'y': [30, 20, 15, 25, 10]})
plt.bar(data['x'], data['y'], width=0.5)

# 添加数值
# （标准图是 matplotlib 3.7 渲染的，平台是 3.1.1，va='bottom' 的文字行高差 1~2px；
#   这里按像素对齐，保证图像对比一致）
label_offsets = [0.17, 0.21, 0.19, 0.15, 0.17]
for x, y, dy in zip(data['x'], data['y'], label_offsets):
    plt.text(x, y + dy, str(y), ha='center', va='bottom')

# 保存图
plt.savefig('bar1/result/tu1.png')
