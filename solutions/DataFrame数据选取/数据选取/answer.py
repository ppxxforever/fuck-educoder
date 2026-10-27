import pandas as pd

df = pd.read_csv('603000sh.csv')
print(df.loc[10:20, ['ts_code', 'trade_date', 'vol']])