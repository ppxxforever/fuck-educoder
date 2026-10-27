import pandas as pd

df = pd.read_excel('ClassScore.xls', index_col=0)

print(df.iloc[1:3])
print(df.iloc[1:3, :2])
print(df.iloc[[0, 2], [0, 2]])