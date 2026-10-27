#画2012年全球地震散点图
#导入numpy库、matplotlib.pyplot模块及matplotlib.font_manager模块、pandas库
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import pandas as pd

#设置中文字体及字号(fname='simhei.ttf', size=14)
font = FontProperties(fname='simhei.ttf', size=14)

#读入文件'全球2012年地震.csv'
data = pd.read_csv('earthquake2012.csv')

#读入'Depth'列数据的10:12600行
depth = data['Depth'].iloc[10:12600]

#读入'Magnitude'列数据的10:12600行
magnitude = data['Magnitude'].iloc[10:12600]

#绘制标题文字('2012年全球地震散点图', fontproperties = font)
plt.title('2012年全球地震散点图', fontproperties=font)

#绘制x坐标说明('震源深度(km)', fontproperties = font)
plt.xlabel('震源深度(km)', fontproperties=font)

#绘制y坐标说明('地震级别', fontproperties=font)
plt.ylabel('地震级别', fontproperties=font)

#绘制散点图
plt.scatter(depth, magnitude, c='#FF1212', s=20)

#保存图形
plt.savefig('t0803/result/tu3.png')
