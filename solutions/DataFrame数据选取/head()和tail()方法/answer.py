import pandas as pd

df = pd.read_excel('ClassScore.xls', index_col='学号')
print(df.head(3))
print(df.tail(5))