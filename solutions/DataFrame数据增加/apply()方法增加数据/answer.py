import pandas as pd

pd.set_option('display.max_rows', 10)

df = pd.read_excel('ClassScore.xls', index_col=0)

df['平时成绩'] = pd.to_numeric(df['平时成绩'], errors='coerce')
df['期末成绩'] = pd.to_numeric(df['期末成绩'], errors='coerce')

def get_total(row):
    score1 = row['平时成绩']
    score2 = row['期末成绩']
    return 0.4 * score1 + 0.6 * score2

df['总评成绩'] = df.apply(get_total, axis=1)

print(df)