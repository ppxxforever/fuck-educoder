"""
任务：自定义函数calculate，实现 2 个数之间的加、减、乘、除运算，并返回结果值。
函数calculate接收三个参数，其中第一个参数为符号判断值，第二个参数为第一个运算数，
第三个参数为第二个运算数。符号判断值有4个，分别为1、2、3、4，依次对应加、减、乘、
除运算。
"""
# 定义函数calculate
def calculate(sign,var1,var2):
    # 请在下面的Begin-End之间按照注释中给出的提示编写正确的代码
    ########### Begin ###########
    # 第一步：判断sign是否等于1，等于1的话，进行加法运算，并将结果赋值给temp
    if sign == 1:
        temp = var1 + var2
    # 第二步：判断sign是否等于2，等于2的话，进行减法运算，并将结果赋值给temp
    elif sign == 2:
        temp = var1 - var2
    # 第三步：判断sign是否等于3，等于3的话，进行乘法运算，并将结果赋值给temp
    elif sign == 3:
        temp = var1 * var2
    # 判断sign是否等于4，等于4的话，进行除法运算
    else:
        # 判断被除数var2是否等于0，等于0的话，返回“被除数var2不能是0！”
        if var2 == 0:
            return '被除数var2不能是0！'
        # 第四步：被除数var2不等于0，进行除法运算，并将结果赋值给temp
        temp = var1 / var2
    ########### End ###########
    return temp     # 返回结果值


sign = int(input())     # 从后台获取数据sign
var1 = int(input())     # 从后台获取数据var1
var2 = int(input())     # 从后台获取数据var2
result = calculate(sign,var1,var2)     # 得到计算结果
print(result)     # 打印计算结果