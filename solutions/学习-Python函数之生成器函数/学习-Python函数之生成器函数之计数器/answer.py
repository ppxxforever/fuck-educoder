"""
任务：设计一个生成器函数 count()，每次使用 next 函数调用该函数时，数字就会加 1。请编写代码实现一个从 0 开始的计数器。
"""

 
# 请在下面的Begin-End之间按照注释中给出的提示编写正确的代码
########## Begin ##########
# 定义生成器函数count(),实现一个从0开始的计数器
def count():
    n = 0
    while True:
        yield n
        n += 1
 
########## End ##########
func = count()
num = int(input())
for x in range(num):
	print(next(func))