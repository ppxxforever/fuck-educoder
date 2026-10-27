"""程序代码
任务：自定义函数 ScoreAverage，该函数的作用是计算学生成绩的平均分，但是学生人数未知；
成绩的输入方式通过给函数传递参数来实现，请编写代码实现计算平均分。
"""
 
#请在下面的Begin-End之间按照注释中给出的提示编写正确的代码
##########Begin##########
# 使用可变参数实现函数的功能，返回学生成绩的平均分
def ScoreAverage(*scores):
    return sum(scores) / len(scores)
##########End##########
# eval()是Python的内置函数，它能将字符串转换为可执行的表达式，并返回表达式的值
score = eval(input())
print("平均分为",score)