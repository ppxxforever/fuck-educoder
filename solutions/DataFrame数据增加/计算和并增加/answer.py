import pandas as pd
import ast

data = ast.literal_eval(input())
df = pd.DataFrame(data)

df['s0'] = df.sum(axis=1)
df.loc['s1'] = df.sum(axis=0)

print(df)