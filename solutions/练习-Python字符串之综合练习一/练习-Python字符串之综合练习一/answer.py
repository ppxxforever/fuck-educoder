str1 = input()     # 包含邮箱号的字符串

# 请在下面的Begin-End之间按照注释中给出的提示编写正确的代码
########## Begin ##########
# 使用字符串函数筛选出这些邮箱号，并根据不同的电子邮件服务商来分类
emails = str1.split(',')
groups = {}
for email in emails:
    email = email.strip()
    if '@' not in email:
        continue
    provider = email.split('@')[1].split('.com')[0]
    if provider not in groups:
        groups[provider] = []
    groups[provider].append(email)

result = []
for provider in sorted(groups.keys()):
    result.append(provider + ':' + ','.join(groups[provider]))
########## End ##########

print(result)