#导入numpy库
import numpy as np

#导入matplotlib.pyplot库
import matplotlib.pyplot as plt

#导入字体管理模块
from matplotlib.font_manager import FontProperties

#设置中文字体及字号
font = FontProperties(fname='simhei.ttf', size=14)
title_font = FontProperties(fname='simhei.ttf', size=24)

#给变量x和y赋值
x = [2014, 2015, 2016, 2017, 2018, 2019, 2020]
y = [300, 350, 500, 800, 650, 750, 660]

#设置图形的长和高为(8, 5)
plt.figure(figsize=(8, 5))

#调用plot方法绘图
plt.plot(x, y, 'b--o', linewidth=1)

#设置x轴标签
plt.xlabel('时间(年)', fontproperties=font)

#设置y轴标签
plt.ylabel('产值(万元)', fontproperties=font)

#绘制图片标题
plt.title('xxx企业年产值', fontproperties=title_font)

#绘制注释文字
plt.text(2019, 760, '近年均值', fontproperties=font, ha='center')

#保存图片
plt.savefig('t0801/result/tu1.png')
