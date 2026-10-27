"""
任务：给定一个嵌套列表，递归实现嵌套列表求和，打印求和后的结果。
"""
list1 = eval(input())
 
# 请在下面的Begin-End之间按照注释中给出的提示编写正确的代码
########## Begin ##########
# 定义一个函数，递归实现嵌套列表求和,打印求和后的结果
def recursive_sum(lst):
    total = 0
    for item in lst:
        if isinstance(item, list):
            total += recursive_sum(item)
        else:
            total += item
    return total

print(recursive_sum(list1))
########## End ##########