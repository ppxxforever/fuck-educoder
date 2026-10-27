import sys
import ast
import pandas as pd

lines = [line.strip() for line in sys.stdin if line.strip()]
dict1 = ast.literal_eval(lines[0])
dict2 = ast.literal_eval(lines[1])

df1 = pd.DataFrame(dict1).set_index('c1')
df2 = pd.DataFrame(dict2).set_index('c1')

result = pd.merge(df1, df2, left_index=True, right_index=True, how='inner')
result.index.name = 'c1'

print(result)