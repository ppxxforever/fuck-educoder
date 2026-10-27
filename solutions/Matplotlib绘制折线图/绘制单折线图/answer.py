# 导入pyplot子模块
import matplotlib.pyplot as plt

# 设中文字体为黑体
plt.rcParams['font.sans-serif'] = 'SimHei'
# 解决负号不能显示问题
plt.rcParams['axes.unicode_minus'] = False
# x坐标值列表
x = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022]
# y坐标值列表
y = [500, 550, 600, 700, 800, 750, 700, 720]
# 绘图
plt.plot(x, y, 'r--o', linewidth=4)
# 添加x轴标签
plt.xlabel('时间(年)', fontsize=14)
# 添加y轴标签
plt.ylabel('销售额(万元)', fontsize=14)
# 添加图形标题
plt.title('某企业年销售额', fontsize=24)
# 保存图
plt.savefig('Z1/result/tu1.png')
