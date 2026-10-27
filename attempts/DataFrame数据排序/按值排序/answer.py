import pandas as pd

df = pd.read_csv('temperature.txt', sep='\s+', engine='python', index_col=0)
df.columns = ['城市', '最高温度', '最低温度']

df['最高温度'] = df['最高温度'].str.replace('℃', '').astype(int)
df['最低温度'] = df['最低温度'].str.replace('℃', '').astype(int)

df_sorted1 = df.sort_values(by='最高温度', ascending=True, kind='mergesort')
print(df_sorted1)

df_sorted2 = df.sort_values(by=['最高温度', '最低温度'], ascending=[True, False], kind='mergesort')
print(df_sorted2)