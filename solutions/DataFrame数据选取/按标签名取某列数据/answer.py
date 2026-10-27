import pandas as pd

df = pd.read_excel('ClassScore.xls')
df.set_index('学号', inplace=True)
pd.set_option('display.max_rows', 10)
print(df['姓名'])