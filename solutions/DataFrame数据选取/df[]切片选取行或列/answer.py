import pandas as pd

pd.set_option('display.max_rows', 4)

df = pd.read_excel('ClassScore.xls', index_col='学号')
df['年龄'] = pd.to_numeric(df['年龄'], errors='coerce')

print(df.head(3))
print(df['姓名'])
print(df[['姓名', '年龄']])
print(df[df['年龄'] > 21])