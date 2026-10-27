import pandas as pd

s1 = pd.Series([2, 4, 6], index=['A', 'B', 'C'])
s2 = pd.Series({'a': 1, 'b': 2, 'c': 3})

print(s1, end=' \n\n')
print(s2, end=' \n')