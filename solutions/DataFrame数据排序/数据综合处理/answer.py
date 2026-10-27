import pandas as pd

pd.set_option('display.max_rows', 8)
pd.set_option('display.max_columns', None)

df = pd.read_excel('stock.xlsx')
df['New'] = (df['close'] - df['low']).round(2)
df = df.sort_values(by=['New', 'close'], ascending=[True, False])
result = df[['ts_code', 'open', 'close', 'New']]
print(result)