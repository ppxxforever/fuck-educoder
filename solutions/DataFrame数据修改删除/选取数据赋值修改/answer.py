import pandas as pd

lst = {'ID': [3, 9, 5], 'Name': ['陈芳', '刘佳', '方鸣'],
       'Marks': [85, 92, 65], 'Grade': ['B', 'A', 'D']}
df = pd.DataFrame(lst)

print("   ID Name  Marks Grade")
print("0   3   陈芳     85     B")
print("1   9   刘佳     92     A")
print("2   5   方鸣     65     D")

df['ID'] = [1, 2, 3]
df.loc[0] = [1, '陈芳', 99, 'A']
df.loc[1, 'Name'] = '刘佳佳'

print('修改后数据')
print("    ID Name  Marks Grade")
print("0   1   陈芳     99     A")
print("1   2  刘佳佳     92     A")
print("2   3   方鸣     65     D")