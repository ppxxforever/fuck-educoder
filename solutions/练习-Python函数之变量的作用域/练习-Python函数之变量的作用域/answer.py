"""
任务：使用变量作用域相关的关键字修改下方 Begin-End 之间的代码，使 max_value 函数实现求最大值的功能。
"""
 
# 请在下面的Begin-End之间按照注释中给出的提示编写正确的代码
########## Begin ##########
# 使用变量作用域相关的关键字修改代码，使max_value函数实现求最大值的功能
def compare(x,y):
	return x if x > y else y

def max_value(*list_data):
	global value
	value = list_data[0]
	for x in range(1,len(list_data)):
		value = compare(list_data[x],value)
########## End ##########

value = 0
max_value(42323,457,4245,6,3,5463,6,7,45,725,723,7,3,46,86,7,56,8,567,5,5745,26,34,63,412,35,4,76585,67,3,45,4,5,34,5,47,5686)
print(value)