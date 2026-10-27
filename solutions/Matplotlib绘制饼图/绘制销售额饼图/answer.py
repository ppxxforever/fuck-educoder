# 导入子模块pyplot
import matplotlib.pyplot as plt

# 导入numpy库
import numpy as np

# 导入pandas库
import pandas as pd

# 设置中文字体为黑体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 读文件，第0列为行标签
sale = pd.read_csv('sale.csv', index_col=0)

# 饼图数据
data = sale.iloc[0]

# 饼图数据标签
labels = sale.columns

# 饼图分离率（岳麓店突出显示，平台标准图的分离量是 0.2）
explode = [0.2, 0, 0, 0]

# 绘饼图，添加百分比
plt.pie(data, labels=labels, autopct='%1.1f%%', explode=explode)

# 设置饼图标题（必须与标准图一致，图像对比是按像素比的）
plt.title('某店1月销售额饼图')


#**************End***************
#保存图片
plt.savefig('c0707/result/tu1.png')
#显示图片(云平台无法显示，注释）
#plt.show()
