"""
任务：定义一个 compare 函数和一个嵌套函数 max_value，compare 函数用于比较两个数的大小，max_value 函数用于得到一串整型数据中的最大值。
"""

 
# 请在下面的Begin-End之间按照注释中给出的提示编写正确的代码
##########Begin##########
# 使用函数的嵌套定义完成两个函数的创建
def max_value(data):
    def compare(a, b):
        if a > b:
            return a
        return b
    result = data[0]
    for item in data[1:]:
        result = compare(result, item)
    return result

##########End##########
# 请勿修改下列函数调用的代码
max_number = max_value(eval(input()))     # eval(input())是将输入的字符串转换为列表
print(max_number)