"""
任务：在编写代码时，我们规定在代码末尾注释时需要给定 5 个空格来隔开。以字符串的形式给定一行代码，请使用字符串函数将代码中的注释修改为符合要求的形式。打印修改后的代码。
"""
 
code = input()
 
# 请在下面的Begin-End之间按照注释中给出的提示编写正确的代码
########## Begin ##########
# 第一步：切分出注释部分代码
parts = code.split('#', 1)

# 第二步：使用合适的字符串函数来处理注释代码
if len(parts) == 2:
    code_part = parts[0].rstrip()
    comment_part = parts[1].strip()
    print(code_part + '     # ' + comment_part)
else:
    print(code)
########## End ##########