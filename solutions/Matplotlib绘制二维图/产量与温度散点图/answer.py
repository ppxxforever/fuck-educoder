#导入第三方库
import matplotlib.pyplot as plt
import numpy as np
#解决中文显示问题
plt.rcParams['font.sans-serif'] = ['SimHei']
#解决负号显示问题
plt.rcParams['axes.unicode_minus'] = False

#定义产量数据
production = [1125, 1725, 2250, 2875, 2900, 3750, 4125]
#定义温度数据
tem = [6, 8, 10, 13, 14, 16, 21]
#定义降水量数据
rain = [25, 40, 58, 68, 110, 98, 120]
#颜色数组
colors = ['r','g','b','k','y','c','m']
size = production
#画散点图，透明度为0.6
plt.scatter(tem, rain, s=size, c=colors, alpha=0.6)

#纵坐标轴范围[0, 150]
plt.ylim(0, 150)

#横坐标轴范围[0, 30]
plt.xlim(0, 30)

#横坐标轴标题为'温度'
plt.xlabel('温度')

#纵坐标轴标题为'降雨量'
plt.ylabel('降雨量')

#***************End**********
#显示图形
#plt.show()
#保存图形
plt.savefig('t0802/result/tu2.png')