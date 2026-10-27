"""
任务：创建函数 circle_area，它有一个参数，表示圆的半径，半径值通过 input 函数获取。该函数用于实现圆的面积计算，并返回面积结果。
"""

import math

# 请在下面的Begin-End之间按照注释中给出的提示编写正确的代码
########## Begin ##########
# 第一步：创建函数 circle_area
def circle_area(r):
    # 第二步：计算圆的面积计算，并返回面积结果
    return math.pi * r * r

########## End ##########
r = float(input())
area = circle_area(r)
print("圆的面积为",area)